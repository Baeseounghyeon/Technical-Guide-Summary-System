"""2단계 작업 처리기: 파트너 가이드 파싱·목차 매칭 → 오류 탐지 → 수정본·보고서 생성."""

import asyncio
import re
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    CorrectionExport,
    ExportStatus,
    Finding,
    FindingStatus,
    Job,
    JobKind,
    PartnerGuide,
    PartnerGuideStatus,
    PartnerSection,
    Section,
    User,
)
from .exporters.corrections import ReportRow, TrackedChange, build_report_docx, build_tracked_docx
from .llm import CompareInput, LLMProvider, TocEntry, get_provider
from .llm.base import FINDING_CATEGORIES, SEVERITIES
from .parsing import parse_source
from .jobs import JobPaused, has_time_for_llm_call
from .pipeline import _local
from .storage import get_storage

_SPACES = re.compile(r"\s+")


# ---------- 1. 파싱 + 목차 매칭 ----------


def handle_parse_partner_guide(db: Session, job: Job) -> None:
    pg = db.get(PartnerGuide, job.payload["partner_guide_id"])
    pg.status = PartnerGuideStatus.PARSING
    db.commit()

    with get_storage().local_path(pg.file_path) as path:
        parsed = parse_source(pg.source_type, path=path)
    pg.sections.clear()
    db.flush()
    for index, ps in enumerate(parsed.sections):
        pg.sections.append(
            PartnerSection(
                order_index=index,
                level=ps.level,
                title=ps.title[:500],
                page_start=ps.page_start,
                page_end=ps.page_end,
                text=ps.text,
            )
        )
    pg.title = pg.title or parsed.title or job.payload.get("fallback_title")
    db.flush()

    partner_entries = [_toc_entry(s.id, s.title, s.text) for s in pg.sections if s.text.strip()]
    vendor_entries = [_toc_entry(s.id, s.title, s.text) for s in _vendor_sections(pg)]
    mapping = asyncio.run(get_provider().match_sections(partner_entries, vendor_entries)) if partner_entries else {}
    for s in pg.sections:
        s.matched_section_id = mapping.get(s.id)
        s.match_method = "auto" if s.matched_section_id else None

    pg.status = PartnerGuideStatus.MATCHED
    pg.error = None
    db.commit()


def fail_parse_partner_guide(db: Session, job: Job, error: str) -> None:
    pg = db.get(PartnerGuide, job.payload["partner_guide_id"])
    pg.status = PartnerGuideStatus.FAILED
    pg.error = error


# ---------- 2. 오류 탐지 ----------


def handle_compare_partner_guide(db: Session, job: Job) -> None:
    pg = db.get(PartnerGuide, job.payload["partner_guide_id"])
    targets = [s for s in pg.sections if s.matched_section_id and s.text.strip()]
    if not job.payload.get("started"):
        # 아직 결정하지 않은 후보만 지우고 다시 찾는다. 수락·거절한 기록은 이력으로 남긴다.
        for finding in [f for f in pg.findings if f.status == FindingStatus.OPEN]:
            pg.findings.remove(finding)
        pg.status = PartnerGuideStatus.COMPARING
        pg.progress_current, pg.progress_total = 0, len(targets)
        pg.error = None
        job.payload = {**job.payload, "started": True, "done": [], "errors": []}
        db.commit()

    # 시간 제한(서버리스)으로 멈췄다가 이어서 할 때는 아직 비교하지 않은 항목만 처리한다.
    done = set(job.payload["done"])
    asyncio.run(_compare_many(db, get_provider(), pg, [s for s in targets if s.id not in done], job))
    if len(job.payload["done"]) < len(targets):
        raise JobPaused
    pg.status = PartnerGuideStatus.REVIEWING
    pg.error = "\n".join(job.payload["errors"]) or None
    db.commit()


async def _compare_many(
    db: Session, provider: LLMProvider, pg: PartnerGuide, targets: list[PartnerSection], job: Job
) -> None:
    guide = pg.guide
    vendor_sections = guide.document.sections
    summaries = {s.section_id: s.content for s in guide.summaries}
    decided = {(f.partner_section_id, f.before_text) for f in pg.findings}
    inputs = {
        s.id: CompareInput(
            vendor=guide.document.vendor.name,
            target_language=guide.target_language,
            partner_title=s.title,
            partner_text=s.text,
            vendor_title=s.matched_section.title,
            vendor_text=_with_descendants(s.matched_section, vendor_sections, lambda x: x.text),
            summary_text=_with_descendants(s.matched_section, vendor_sections, lambda x: summaries.get(x.id, "")),
        )
        for s in targets
    }
    semaphore = asyncio.Semaphore(settings.llm_concurrency)

    async def run(section: PartnerSection) -> None:
        async with semaphore:
            if not has_time_for_llm_call():
                return  # 시간 제한: 다음 처리 때 이어서 한다
            errors: list[str] = []
            try:
                results = await provider.compare_section(inputs[section.id])
            except Exception as e:  # 한 섹션 실패가 전체를 멈추지 않도록 기록만 한다.
                errors.append(f"'{section.title}' 비교 실패: {type(e).__name__}: {e}"[:500])
            else:
                for r in results:
                    if not r.before.strip() or r.before == r.after or (section.id, r.before) in decided:
                        continue
                    decided.add((section.id, r.before))
                    pg.findings.append(
                        Finding(
                            partner_section_id=section.id,
                            vendor_section_id=section.matched_section_id,
                            category=r.category if r.category in FINDING_CATEGORIES else "contradiction",
                            severity=r.severity if r.severity in SEVERITIES else "medium",
                            before_text=r.before,
                            after_text=r.after,
                            reason=r.reason,
                            evidence=r.evidence,
                            locatable=r.before in section.text,
                        )
                    )
            pg.progress_current += 1
            job.payload = {
                **job.payload,
                "done": job.payload["done"] + [section.id],
                "errors": job.payload["errors"] + errors,
            }
            db.commit()

    await asyncio.gather(*(run(s) for s in targets))


def fail_compare_partner_guide(db: Session, job: Job, error: str) -> None:
    pg = db.get(PartnerGuide, job.payload["partner_guide_id"])
    pg.status = PartnerGuideStatus.REVIEWING if pg.findings else PartnerGuideStatus.MATCHED
    pg.error = error


# ---------- 3. 수정본(변경 내용 추적) · 수정 보고서 ----------


def handle_export_correction(db: Session, job: Job) -> None:
    export = db.get(CorrectionExport, job.payload["export_id"])
    pg = export.partner_guide
    name = f"partner{pg.id}_{export.kind}_{export.id}.docx"
    with tempfile.TemporaryDirectory() as tmp:
        out_path = Path(tmp) / name
        _build_correction(db, export, pg, out_path)
        export.file_path = get_storage().save(f"corrections/{name}", out_path.read_bytes())
    export.status = ExportStatus.DONE
    db.commit()


def _build_correction(db: Session, export: CorrectionExport, pg: PartnerGuide, out_path: Path) -> None:
    names = _user_names(db, {f.decided_by for f in pg.findings} | {export.created_by})

    if export.kind == "tracked":
        accepted = [f for f in pg.findings if f.status == FindingStatus.ACCEPTED]
        changes = [TrackedChange(f.id, f.before_text, f.final_text or f.after_text) for f in accepted]
        with get_storage().local_path(pg.file_path) as source:
            applied = build_tracked_docx(source, changes, names.get(export.created_by, "검토자"), export.created_at, out_path)
        export.applied_count = len(applied)
        export.skipped_count = len(accepted) - len(applied)
    else:
        rows = [
            ReportRow(
                section=f.partner_section.title,
                category=f.category,
                severity=f.severity,
                before=f.before_text,
                after=(f.final_text or f.after_text) if f.status == FindingStatus.ACCEPTED else f.after_text,
                reason=f.reason,
                evidence=_evidence(f),
                status=f.status,
                decided=f"{names.get(f.decided_by, '')} · {_local(f.decided_at):%Y-%m-%d}" if f.decided_at else "",
                note=f.decision_note or "",
            )
            for f in pg.findings
        ]
        build_report_docx(
            partner_title=pg.title or "파트너 가이드",
            vendor=pg.guide.document.vendor.name,
            guide_title=pg.guide.document.title or "",
            created_at=_local(export.created_at),
            rows=rows,
            out_path=out_path,
        )


def fail_export_correction(db: Session, job: Job, error: str) -> None:
    export = db.get(CorrectionExport, job.payload["export_id"])
    export.status = ExportStatus.FAILED
    export.error = error


# ---------- 공통 ----------


def _vendor_sections(pg: PartnerGuide) -> list[Section]:
    return [s for s in pg.guide.document.sections if s.included]


def _toc_entry(key: int, title: str, text: str) -> TocEntry:
    return TocEntry(key=key, title=title, excerpt=_SPACES.sub(" ", text)[:300])


def _with_descendants(section: Section, all_sections: list[Section], value) -> str:
    """상위 목차가 매칭되면 하위 목차 내용까지 함께 비교 근거로 쓴다."""
    children: dict[int | None, list[Section]] = {}
    for s in all_sections:
        children.setdefault(s.parent_id, []).append(s)
    parts: list[str] = []

    def walk(node: Section) -> None:
        if text := value(node):
            parts.append(f"[{node.title}]\n{text}")
        for child in children.get(node.id, []):
            walk(child)

    walk(section)
    return "\n\n".join(parts)


def _evidence(f: Finding) -> str:
    page = ""
    if f.vendor_section and f.vendor_section.page_start:
        page = f" (원본 p.{f.vendor_section.page_start})"
    return f"{f.evidence}{page}"


def _user_names(db: Session, ids: set[int | None]) -> dict[int, str]:
    ids = {i for i in ids if i}
    return {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}


HANDLERS = {
    JobKind.PARSE_PARTNER_GUIDE: (handle_parse_partner_guide, fail_parse_partner_guide),
    JobKind.COMPARE_PARTNER_GUIDE: (handle_compare_partner_guide, fail_compare_partner_guide),
    JobKind.EXPORT_CORRECTION: (handle_export_correction, fail_export_correction),
}
