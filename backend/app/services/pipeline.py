"""Worker 가 실행하는 작업 처리기: 파싱 → 요약 → (재생성) → 문서 생성."""

import asyncio
import re
import tempfile
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    DocStatus,
    Export,
    ExportStatus,
    GlossaryTerm,
    Guide,
    GuideStatus,
    Job,
    JobKind,
    Partner,
    Section,
    SectionSummary,
    SourceDocument,
    SummaryRevision,
    SummaryStatus,
)
from .jobs import JobPaused, has_time_for_llm_call
from .exporters import ExportContext, ExportSection, build_docx, build_pptx
from .llm import LLMProvider, OverviewInput, SectionInput, SectionResult, get_provider
from .parsing import is_boilerplate, parse_source
from .storage import get_storage
from .usage import budget_exceeded

# ---------- 1. 문서 파싱 ----------


def handle_parse_document(db: Session, job: Job) -> None:
    doc = db.get(SourceDocument, job.payload["document_id"])
    doc.status = DocStatus.PARSING
    db.commit()

    with ExitStack() as stack:
        path = stack.enter_context(get_storage().local_path(doc.file_path)) if doc.file_path else None
        parsed = parse_source(doc.source_type, path=path, url=doc.url)
    doc.sections.clear()
    db.flush()

    stack: list[Section] = []
    for index, ps in enumerate(parsed.sections):
        while stack and stack[-1].level >= ps.level:
            stack.pop()
        section = Section(
            parent=stack[-1] if stack else None,
            order_index=index,
            level=ps.level,
            title=ps.title[:500],
            page_start=ps.page_start,
            page_end=ps.page_end,
            text=ps.text,
            included=not is_boilerplate(ps.title),
        )
        doc.sections.append(section)
        stack.append(section)

    doc.page_count = parsed.page_count
    doc.title = doc.title or parsed.title or job.payload.get("fallback_title")
    doc.status = DocStatus.PARSED
    doc.error = None
    db.commit()


def fail_parse_document(db: Session, job: Job, error: str) -> None:
    doc = db.get(SourceDocument, job.payload["document_id"])
    doc.status = DocStatus.FAILED
    doc.error = error


# ---------- 2. 요약 + 번역 ----------


def handle_summarize_guide(db: Session, job: Job) -> None:
    guide = db.get(Guide, job.payload["guide_id"])
    guide.status = GuideStatus.SUMMARIZING
    resumed = bool(job.payload.get("started"))
    if resumed:
        # 시간 제한으로 멈췄다가 이어서 하는 경우: 끝나지 않은 것만 (실패한 것은 다시 시도하지 않는다)
        retry = (SummaryStatus.PENDING, SummaryStatus.GENERATING)
    else:
        retry = (SummaryStatus.PENDING, SummaryStatus.FAILED)
        job.payload = {**job.payload, "started": True}
    targets = [s for s in guide.summaries if s.status in retry]
    for s in targets:
        s.status = SummaryStatus.PENDING
    if not resumed:
        job.progress_total = len(targets)
    if budget_exceeded(db):
        # 전체 월 예산을 넘으면 남은 항목은 멈춘다 (예산이 늘거나 다음 달에 '코멘트로 재생성'으로 다시 만들 수 있다)
        for s in targets:
            s.status, s.error = SummaryStatus.FAILED, "이번 달 AI 사용 예산을 모두 사용해 중단했습니다."
        guide.status = GuideStatus.REVIEWING
        db.commit()
        return
    db.commit()

    provider = get_provider()
    asyncio.run(_summarize_many(db, provider, guide, targets, job))
    if any(s.status == SummaryStatus.PENDING for s in targets) or not has_time_for_llm_call():
        raise JobPaused

    drafted = [s for s in _ordered_summaries(guide) if s.content]
    if drafted:
        guide.overview = asyncio.run(
            provider.summarize_overview(
                OverviewInput(
                    vendor=guide.document.vendor.name,
                    document_title=guide.document.title or "",
                    target_language=guide.target_language,
                    sections=[(s.section.title, s.content) for s in drafted],
                )
            )
        )
    guide.status = GuideStatus.REVIEWING
    db.commit()


async def _summarize_many(
    db: Session, provider: LLMProvider, guide: Guide, targets: list[SectionSummary], job: Job
) -> None:
    glossary = _glossary(db, guide)
    inputs = {s.id: _section_input(guide, s.section, glossary) for s in targets}
    semaphore = asyncio.Semaphore(settings.llm_concurrency)

    async def run(summary: SectionSummary) -> None:
        async with semaphore:
            if not has_time_for_llm_call():
                return  # 시간 제한: PENDING 으로 남겨 다음 처리 때 이어서 한다
            summary.status = SummaryStatus.GENERATING
            db.commit()
            try:
                result = await provider.summarize_section(inputs[summary.id])
            except Exception as e:  # 한 섹션 실패가 전체를 멈추지 않도록 기록만 한다.
                summary.status = SummaryStatus.FAILED
                summary.error = f"{type(e).__name__}: {e}"[:2000]
            else:
                apply_result(summary, result, origin="generated")
            job.progress_current += 1
            db.commit()

    await asyncio.gather(*(run(s) for s in targets))


def fail_summarize_guide(db: Session, job: Job, error: str) -> None:
    guide = db.get(Guide, job.payload["guide_id"])
    for s in guide.summaries:
        if s.status in (SummaryStatus.PENDING, SummaryStatus.GENERATING):
            s.status = SummaryStatus.FAILED
            s.error = error
    guide.status = GuideStatus.REVIEWING


# ---------- 3. 피드백 반영 재생성 ----------


def handle_regenerate_section(db: Session, job: Job) -> None:
    if not has_time_for_llm_call():
        raise JobPaused
    summary = db.get(SectionSummary, job.payload["summary_id"])
    guide = summary.guide
    item = _section_input(guide, summary.section, _glossary(db, guide))
    item.previous_summary = summary.content
    item.feedback = job.payload["comment"]

    result = asyncio.run(get_provider().summarize_section(item))
    apply_result(summary, result, origin="regenerated", comment=item.feedback, author_id=job.payload.get("author_id"))
    guide.status = GuideStatus.REVIEWING
    db.commit()


def fail_regenerate_section(db: Session, job: Job, error: str) -> None:
    summary = db.get(SectionSummary, job.payload["summary_id"])
    # 기존 내용은 그대로 두고 다시 검토할 수 있게 초안 상태로 되돌린다.
    summary.status = SummaryStatus.DRAFT if summary.content else SummaryStatus.FAILED
    summary.error = f"재생성 실패: {error}"


# ---------- 4. Word / PPT 생성 ----------


def handle_export_guide(db: Session, job: Job) -> None:
    export = db.get(Export, job.payload["export_id"])
    safe_version = re.sub(r"[^\w.-]", "_", export.doc_version)
    name = f"guide{export.guide_id}_v{safe_version}_{export.id}.{export.format}"
    storage = get_storage()
    with ExitStack() as stack:
        ctx = _export_context(db, export, stack)
        out_path = Path(stack.enter_context(tempfile.TemporaryDirectory())) / name
        (build_docx if export.format == "docx" else build_pptx)(ctx, out_path)
        export.file_path = storage.save(f"exports/{name}", out_path.read_bytes())
    export.status = ExportStatus.DONE
    db.commit()


def fail_export_guide(db: Session, job: Job, error: str) -> None:
    export = db.get(Export, job.payload["export_id"])
    export.status = ExportStatus.FAILED
    export.error = error


def _export_context(db: Session, export: Export, stack: ExitStack) -> ExportContext:
    """로고·양식은 저장소에서 로컬 경로로 받아 stack 이 닫힐 때까지 유지한다."""
    guide = export.guide
    doc = guide.document
    partner_id = export.partner_id or doc.partner_id
    partner = db.get(Partner, partner_id) if partner_id else None
    summaries = {s.section_id: s for s in guide.summaries}

    sections = []
    for sec in doc.sections:
        if not sec.included:
            continue
        s = summaries.get(sec.id)
        sections.append(
            ExportSection(
                title=sec.title,
                level=sec.level,
                content=s.content if s else None,
                key_steps=list(s.key_steps) if s else [],
                warnings=list(s.warnings) if s else [],
                page_start=sec.page_start,
                page_end=sec.page_end,
            )
        )

    # 같은 버전을 Word 와 PPT 로 각각 만들 수 있으므로 버전당 마지막 기록 한 줄만 남긴다.
    by_version: dict[str, dict] = {}
    for e in guide.exports:
        if e.revision and (e.id == export.id or e.status == ExportStatus.DONE):
            by_version.pop(e.doc_version, None)
            by_version[e.doc_version] = {
                **e.revision,
                "doc_version": e.doc_version,
                "date": f"{_local(e.created_at):%Y-%m-%d}",
            }
    revisions = list(by_version.values())
    template = None
    if export.use_partner_template and partner:
        template = partner.docx_template_path if export.format == "docx" else partner.pptx_template_path

    return ExportContext(
        title=doc.title or "기술 가이드",
        vendor=doc.vendor.name,
        target_language=guide.target_language,
        doc_version=export.doc_version,
        created_at=_local(export.created_at),
        overview=guide.overview,
        sections=sections,
        logo_path=_local_file(stack, partner.logo_path) if export.include_logo and partner and partner.logo_path else None,
        template_path=_local_file(stack, template) if template else None,
        revisions=revisions,
    )


# ---------- 공통 ----------


def _local_file(stack: ExitStack, ref: str) -> Path:
    return stack.enter_context(get_storage().local_path(ref))


def _local(value: datetime) -> datetime:
    """DB 의 UTC 시각을 문서에 표시할 시간대로 바꾼다 (SQLite 는 시간대 정보를 잃는다)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(settings.display_timezone))


def apply_result(
    summary: SectionSummary,
    result: SectionResult,
    *,
    origin: str,
    comment: str | None = None,
    author_id: int | None = None,
) -> None:
    summary.version += 1
    summary.content = result.summary_markdown
    summary.key_steps = result.key_steps
    summary.warnings = result.warnings
    summary.status = SummaryStatus.DRAFT
    summary.error = None
    summary.revisions.append(
        SummaryRevision(
            version=summary.version,
            content=result.summary_markdown,
            origin=origin,
            comment=comment,
            author_id=author_id,
        )
    )


def _ordered_summaries(guide: Guide) -> list[SectionSummary]:
    return sorted(guide.summaries, key=lambda s: s.section.order_index)


def _section_path(section: Section) -> str:
    titles = []
    node: Section | None = section
    while node is not None:
        titles.append(node.title)
        node = node.parent
    return " > ".join(reversed(titles))


def _section_input(guide: Guide, section: Section, glossary: list[tuple[str, str]]) -> SectionInput:
    return SectionInput(
        vendor=guide.document.vendor.name,
        document_title=guide.document.title or "",
        section_path=_section_path(section),
        text=section.text,
        target_language=guide.target_language,
        glossary=glossary,
    )


def _glossary(db: Session, guide: Guide) -> list[tuple[str, str]]:
    rows = db.scalars(
        select(GlossaryTerm).where(
            GlossaryTerm.vendor_id == guide.document.vendor_id,
            GlossaryTerm.target_language == guide.target_language,
        )
    )
    return [(t.source_term, t.target_term) for t in rows]


HANDLERS = {
    JobKind.PARSE_DOCUMENT: (handle_parse_document, fail_parse_document),
    JobKind.SUMMARIZE_GUIDE: (handle_summarize_guide, fail_summarize_guide),
    JobKind.REGENERATE_SECTION: (handle_regenerate_section, fail_regenerate_section),
    JobKind.EXPORT_GUIDE: (handle_export_guide, fail_export_guide),
}
