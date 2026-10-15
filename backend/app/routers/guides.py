"""요약 가이드 생성과 목차 항목별 검토(승인 / 직접 수정 / 코멘트로 재생성)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_active_user, get_document_for_user, get_guide_for_user
from ..models import (
    DocStatus,
    Guide,
    GuideStatus,
    JobKind,
    SectionSummary,
    SummaryRevision,
    SummaryStatus,
    User,
)
from ..schemas import (
    BulkApproveOut,
    GuideBrief,
    GuideCreate,
    GuideDetail,
    GuideItem,
    GuideProgress,
    RegenerateIn,
    RevisionOut,
    SummaryEdit,
    SummaryOut,
)
from ..services.jobs import enqueue

router = APIRouter(prefix="/api", tags=["요약 가이드"])


@router.post("/documents/{document_id}/guides", response_model=GuideBrief, status_code=status.HTTP_201_CREATED)
def create_guide(
    document_id: int, body: GuideCreate, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> Guide:
    doc = get_document_for_user(db, user, document_id)
    if doc.status != DocStatus.PARSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "문서 분석이 끝난 뒤에 요약할 수 있습니다.")
    targets = [s for s in doc.sections if s.included and s.text.strip()]
    if not targets:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "요약할 목차 항목이 없습니다.")

    guide = Guide(document=doc, target_language=body.target_language, created_by=user.id)
    guide.summaries = [SectionSummary(section=s) for s in targets]
    db.add(guide)
    db.flush()
    enqueue(db, JobKind.SUMMARIZE_GUIDE, {"guide_id": guide.id})
    db.commit()
    return guide


@router.get("/guides/{guide_id}", response_model=GuideDetail)
def get_guide(guide_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> GuideDetail:
    guide = get_guide_for_user(db, user, guide_id)
    summaries = {s.section_id: s for s in guide.summaries}
    items = [
        GuideItem(
            section_id=sec.id,
            title=sec.title,
            level=sec.level,
            page_start=sec.page_start,
            page_end=sec.page_end,
            summary=SummaryOut.model_validate(summaries[sec.id]) if sec.id in summaries else None,
        )
        for sec in guide.document.sections
        if sec.included or sec.id in summaries
    ]
    statuses = [s.status for s in guide.summaries]
    return GuideDetail(
        id=guide.id,
        document_id=guide.document_id,
        partner_id=guide.document.partner_id,
        document_title=guide.document.title,
        vendor_name=guide.document.vendor.name,
        target_language=guide.target_language,
        status=guide.status,
        overview=guide.overview,
        progress=GuideProgress(
            total=len(statuses),
            generated=sum(s in (SummaryStatus.DRAFT, SummaryStatus.APPROVED) for s in statuses),
            approved=statuses.count(SummaryStatus.APPROVED),
            failed=statuses.count(SummaryStatus.FAILED),
        ),
        items=items,
    )


@router.post("/guides/{guide_id}/summaries/{summary_id}/approve", response_model=SummaryOut)
def approve_summary(
    guide_id: int, summary_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> SectionSummary:
    summary = _summary(db, user, guide_id, summary_id)
    if summary.status != SummaryStatus.DRAFT:
        raise HTTPException(status.HTTP_409_CONFLICT, "초안 상태의 요약만 승인할 수 있습니다.")
    summary.status = SummaryStatus.APPROVED
    if all(s.status == SummaryStatus.APPROVED for s in summary.guide.summaries):
        summary.guide.status = GuideStatus.APPROVED
    db.commit()
    return summary


@router.post("/guides/{guide_id}/approve-all", response_model=BulkApproveOut)
def approve_all(guide_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> BulkApproveOut:
    """초안 상태인 요약을 한 번에 승인한다. 생성 중·실패·대기 항목은 건드리지 않는다."""
    guide = get_guide_for_user(db, user, guide_id)
    drafts = [s for s in guide.summaries if s.status == SummaryStatus.DRAFT]
    for s in drafts:
        s.status = SummaryStatus.APPROVED
    remaining = sum(s.status != SummaryStatus.APPROVED for s in guide.summaries)
    if remaining == 0 and guide.summaries:
        guide.status = GuideStatus.APPROVED
    db.commit()
    return BulkApproveOut(approved=len(drafts), remaining=remaining, guide_status=guide.status)


@router.put("/guides/{guide_id}/summaries/{summary_id}", response_model=SummaryOut)
def edit_summary(
    guide_id: int, summary_id: int, body: SummaryEdit,
    user: User = Depends(get_active_user), db: Session = Depends(get_db),
) -> SectionSummary:
    """사용자가 직접 고친 내용을 새 버전으로 저장한다. 다시 승인해야 한다."""
    summary = _summary(db, user, guide_id, summary_id)
    if summary.status == SummaryStatus.GENERATING:
        raise HTTPException(status.HTTP_409_CONFLICT, "생성 중인 요약은 수정할 수 없습니다.")
    summary.version += 1
    summary.content = body.content
    summary.status = SummaryStatus.DRAFT
    summary.error = None
    summary.revisions.append(
        SummaryRevision(version=summary.version, content=body.content, origin="edited", author_id=user.id)
    )
    summary.guide.status = GuideStatus.REVIEWING
    db.commit()
    return summary


@router.post("/guides/{guide_id}/summaries/{summary_id}/regenerate", response_model=SummaryOut)
def regenerate_summary(
    guide_id: int, summary_id: int, body: RegenerateIn,
    user: User = Depends(get_active_user), db: Session = Depends(get_db),
) -> SectionSummary:
    summary = _summary(db, user, guide_id, summary_id)
    if summary.status in (SummaryStatus.GENERATING, SummaryStatus.PENDING):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 생성 중입니다.")
    summary.status = SummaryStatus.GENERATING
    summary.guide.status = GuideStatus.REVIEWING
    enqueue(db, JobKind.REGENERATE_SECTION, {"summary_id": summary.id, "comment": body.comment, "author_id": user.id})
    db.commit()
    return summary


@router.get("/guides/{guide_id}/summaries/{summary_id}/revisions", response_model=list[RevisionOut])
def list_revisions(
    guide_id: int, summary_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> list[SummaryRevision]:
    return _summary(db, user, guide_id, summary_id).revisions


def _summary(db: Session, user: User, guide_id: int, summary_id: int) -> SectionSummary:
    guide = get_guide_for_user(db, user, guide_id)
    summary = db.get(SectionSummary, summary_id)
    if summary is None or summary.guide_id != guide.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "요약 항목을 찾을 수 없습니다.")
    return summary
