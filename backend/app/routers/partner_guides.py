"""2단계: 파트너 가이드 업로드 → 목차 매칭 확인 → 오류 탐지 → 수락/거절 → 수정본·보고서."""

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_active_user, get_guide_for_user
from ..models import (
    CorrectionExport,
    CorrectionLog,
    Finding,
    FindingStatus,
    GuideStatus,
    JobKind,
    PartnerGuide,
    PartnerGuideStatus,
    PartnerSection,
    Section,
    User,
    utcnow,
)
from ..schemas import (
    CorrectionExportCreate,
    CorrectionExportOut,
    CorrectionLogOut,
    DecisionIn,
    FindingCounts,
    FindingOut,
    MatchPatch,
    PartnerGuideDetail,
    PartnerGuideOut,
    PartnerSectionOut,
    VendorSectionOption,
)
from ..services.jobs import enqueue
from ..services.parsing import SUPPORTED_EXTENSIONS
from ..services.storage import get_storage
from .uploads import store_upload

router = APIRouter(prefix="/api", tags=["파트너 가이드 비교"])

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.post("/guides/{guide_id}/partner-guides", response_model=PartnerGuideOut, status_code=status.HTTP_201_CREATED)
def upload_partner_guide(
    guide_id: int,
    file: UploadFile | None = File(None),
    storage_key: str | None = Form(None),
    filename: str | None = Form(None),
    title: str | None = Form(None),
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> PartnerGuide:
    guide = get_guide_for_user(db, user, guide_id)
    if guide.status != GuideStatus.APPROVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "모든 항목을 승인한 요약 가이드만 비교 기준으로 쓸 수 있습니다.")
    if file is None and not storage_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "파일을 선택하세요.")
    ext = Path(file.filename or "" if file is not None else storage_key).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "PDF, Word(.docx), PowerPoint(.pptx) 파일만 지원합니다.")
    ref, original_name = store_upload("partner-guides", file, storage_key, filename)

    pg = PartnerGuide(
        guide=guide,
        partner_id=guide.document.partner_id,
        uploaded_by=user.id,
        title=title or None,
        source_type=SUPPORTED_EXTENSIONS[ext],
        file_path=ref,
    )
    db.add(pg)
    db.flush()
    enqueue(db, JobKind.PARSE_PARTNER_GUIDE, {"partner_guide_id": pg.id, "fallback_title": Path(original_name).stem})
    db.commit()
    return pg


@router.get("/guides/{guide_id}/partner-guides", response_model=list[PartnerGuideOut])
def list_partner_guides(guide_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[PartnerGuide]:
    get_guide_for_user(db, user, guide_id)
    return list(db.scalars(select(PartnerGuide).where(PartnerGuide.guide_id == guide_id).order_by(PartnerGuide.id.desc())))


@router.get("/partner-guides/{pg_id}", response_model=PartnerGuideDetail)
def get_partner_guide(pg_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> PartnerGuideDetail:
    pg = _partner_guide(db, user, pg_id)
    doc = pg.guide.document
    names = _user_names(db, {f.decided_by for f in pg.findings})
    statuses = [f.status for f in pg.findings]
    return PartnerGuideDetail(
        **PartnerGuideOut.model_validate(pg).model_dump(),
        vendor_name=doc.vendor.name,
        vendor_document_title=doc.title,
        target_language=pg.guide.target_language,
        sections=[_section_out(s) for s in pg.sections],
        vendor_sections=[VendorSectionOption(id=s.id, title=s.title, level=s.level) for s in doc.sections if s.included],
        findings=[_finding_out(f, names) for f in pg.findings],
        counts=FindingCounts(
            total=len(statuses),
            open=statuses.count(FindingStatus.OPEN),
            accepted=statuses.count(FindingStatus.ACCEPTED),
            rejected=statuses.count(FindingStatus.REJECTED),
        ),
    )


@router.patch("/partner-sections/{section_id}", response_model=PartnerSectionOut)
def update_match(
    section_id: int, body: MatchPatch, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> PartnerSectionOut:
    """자동 매칭이 틀렸을 때 사용자가 대응하는 벤더 목차를 직접 고른다."""
    section = db.get(PartnerSection, section_id)
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "목차 항목을 찾을 수 없습니다.")
    pg = _partner_guide(db, user, section.partner_guide_id)
    if body.matched_section_id is not None:
        vendor = db.get(Section, body.matched_section_id)
        if vendor is None or vendor.document_id != pg.guide.document_id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "기준 문서의 목차 항목이 아닙니다.")
    section.matched_section_id = body.matched_section_id
    section.match_method = "manual"
    db.commit()
    return _section_out(section)


@router.post("/partner-guides/{pg_id}/compare", response_model=PartnerGuideOut)
def start_compare(pg_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> PartnerGuide:
    pg = _partner_guide(db, user, pg_id)
    if pg.status not in (PartnerGuideStatus.MATCHED, PartnerGuideStatus.REVIEWING):
        raise HTTPException(status.HTTP_409_CONFLICT, "목차 매칭이 끝난 뒤에 비교할 수 있습니다.")
    if not any(s.matched_section_id for s in pg.sections):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "벤더 원본과 매칭된 목차가 없습니다.")
    pg.status = PartnerGuideStatus.COMPARING
    enqueue(db, JobKind.COMPARE_PARTNER_GUIDE, {"partner_guide_id": pg.id})
    db.commit()
    return pg


@router.post("/findings/{finding_id}/decision", response_model=FindingOut)
def decide(finding_id: int, body: DecisionIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> FindingOut:
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "오류 후보를 찾을 수 없습니다.")
    _partner_guide(db, user, finding.partner_guide_id)
    note = (body.note or "").strip() or None

    if body.action == "reopen":
        if finding.status == FindingStatus.OPEN:
            raise HTTPException(status.HTTP_409_CONFLICT, "이미 미결정 상태입니다.")
        finding.status, finding.final_text, finding.decided_by, finding.decided_at = FindingStatus.OPEN, None, None, None
        finding.decision_note = note
        after = None
    else:
        if finding.status != FindingStatus.OPEN:
            raise HTTPException(status.HTTP_409_CONFLICT, "이미 결정된 항목입니다. 되돌린 뒤 다시 결정하세요.")
        if body.action == "reject" and not note:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "거절 사유를 메모에 적어 주세요.")
        accepted = body.action == "accept"
        finding.status = FindingStatus.ACCEPTED if accepted else FindingStatus.REJECTED
        finding.final_text = ((body.final_text or "").strip() or finding.after_text) if accepted else None
        finding.decision_note = note
        finding.decided_by, finding.decided_at = user.id, utcnow()
        after = finding.final_text

    db.add(
        CorrectionLog(
            partner_guide_id=finding.partner_guide_id,
            finding_id=finding.id,
            action={"accept": "accepted", "reject": "rejected", "reopen": "reopened"}[body.action],
            before_text=finding.before_text,
            after_text=after,
            reason=finding.reason,
            note=note,
            user_id=user.id,
        )
    )
    db.commit()
    return _finding_out(finding, _user_names(db, {finding.decided_by}))


@router.get("/partner-guides/{pg_id}/history", response_model=list[CorrectionLogOut])
def history(pg_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[CorrectionLogOut]:
    _partner_guide(db, user, pg_id)
    logs = list(
        db.scalars(select(CorrectionLog).where(CorrectionLog.partner_guide_id == pg_id).order_by(CorrectionLog.id.desc()))
    )
    names = _user_names(db, {log.user_id for log in logs})
    return [
        CorrectionLogOut(
            id=log.id,
            finding_id=log.finding_id,
            action=log.action,
            before_text=log.before_text,
            after_text=log.after_text,
            reason=log.reason,
            note=log.note,
            user_name=names.get(log.user_id, ""),
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.post("/partner-guides/{pg_id}/exports", response_model=CorrectionExportOut, status_code=status.HTTP_201_CREATED)
def create_correction_export(
    pg_id: int, body: CorrectionExportCreate, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> CorrectionExport:
    pg = _partner_guide(db, user, pg_id)
    if not pg.findings:
        raise HTTPException(status.HTTP_409_CONFLICT, "비교 결과가 없습니다.")
    if body.kind == "tracked":
        if pg.source_type != "docx":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "변경 내용 추적 수정본은 Word(.docx) 파트너 가이드만 만들 수 있습니다.")
        if not any(f.status == FindingStatus.ACCEPTED for f in pg.findings):
            raise HTTPException(status.HTTP_409_CONFLICT, "수락한 수정이 없습니다.")
    export = CorrectionExport(partner_guide=pg, kind=body.kind, created_by=user.id)
    db.add(export)
    db.flush()
    enqueue(db, JobKind.EXPORT_CORRECTION, {"export_id": export.id})
    db.commit()
    return export


@router.get("/partner-guides/{pg_id}/exports", response_model=list[CorrectionExportOut])
def list_correction_exports(pg_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[CorrectionExport]:
    return _partner_guide(db, user, pg_id).exports


@router.get("/correction-exports/{export_id}/download")
def download_correction_export(export_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    export = db.get(CorrectionExport, export_id)
    if export is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파일을 찾을 수 없습니다.")
    pg = _partner_guide(db, user, export.partner_guide_id)
    if not export.file_path:
        raise HTTPException(status.HTTP_409_CONFLICT, "아직 생성되지 않은 파일입니다.")
    label = "수정본_변경추적" if export.kind == "tracked" else "수정보고서"
    return get_storage().response(export.file_path, f"{pg.title or 'partner-guide'}_{label}.docx", DOCX_MEDIA_TYPE)


def _partner_guide(db: Session, user: User, pg_id: int) -> PartnerGuide:
    pg = db.get(PartnerGuide, pg_id)
    if pg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파트너 가이드를 찾을 수 없습니다.")
    get_guide_for_user(db, user, pg.guide_id)  # 다른 파트너사·도메인이면 404
    return pg


def _section_out(s: PartnerSection) -> PartnerSectionOut:
    return PartnerSectionOut(
        id=s.id,
        order_index=s.order_index,
        level=s.level,
        title=s.title,
        page_start=s.page_start,
        page_end=s.page_end,
        char_count=len(s.text),
        matched_section_id=s.matched_section_id,
        matched_title=s.matched_section.title if s.matched_section else None,
        match_method=s.match_method,
    )


def _finding_out(f: Finding, names: dict[int, str]) -> FindingOut:
    return FindingOut(
        id=f.id,
        partner_section_id=f.partner_section_id,
        partner_section_title=f.partner_section.title,
        vendor_section_title=f.vendor_section.title if f.vendor_section else None,
        vendor_page_start=f.vendor_section.page_start if f.vendor_section else None,
        category=f.category,
        severity=f.severity,
        before_text=f.before_text,
        after_text=f.after_text,
        reason=f.reason,
        evidence=f.evidence,
        locatable=f.locatable,
        status=f.status,
        final_text=f.final_text,
        decision_note=f.decision_note,
        decided_by_name=names.get(f.decided_by) if f.decided_by else None,
        decided_at=f.decided_at,
    )


def _user_names(db: Session, ids: set[int | None]) -> dict[int, str]:
    ids = {i for i in ids if i}
    return {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}
