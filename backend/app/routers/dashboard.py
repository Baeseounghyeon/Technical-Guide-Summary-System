"""로그인한 사용자의 대시보드: 내가 올린 문서의 처리 현황과 문서별 진행 단계."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_active_user
from ..models import DocStatus, ExportStatus, GuideStatus, SourceDocument, SummaryStatus, User
from ..schemas import DashboardCounts, DashboardDocument, DashboardExport, DashboardOut

router = APIRouter(prefix="/api", tags=["대시보드"])

# 진행 단계 → 집계 분류
DONE_STAGES = {"approved", "exported"}
FAILED_STAGES = {"failed"}


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> DashboardOut:
    docs = list(
        db.scalars(
            select(SourceDocument)
            .where(SourceDocument.uploaded_by == user.id, SourceDocument.deleted_at.is_(None))
            .order_by(SourceDocument.created_at.desc())
        )
    )
    rows = [_document_row(d) for d in docs]
    return DashboardOut(
        counts=DashboardCounts(
            total=len(rows),
            completed=sum(r.stage in DONE_STAGES for r in rows),
            in_progress=sum(r.stage not in DONE_STAGES | FAILED_STAGES for r in rows),
            failed=sum(r.stage in FAILED_STAGES for r in rows),
            exports=sum(r.exports for r in rows),
            pending_reviews=sum(r.total_sections - r.approved_sections for r in rows if r.stage == "reviewing"),
        ),
        documents=rows,
    )


def _document_row(doc: SourceDocument) -> DashboardDocument:
    """문서 진행 단계: 분석 중 → 요약 전 → 요약 중 → 검토 중 → 승인 완료 → 문서 생성 완료 (또는 실패)."""
    guide = max(doc.guides, key=lambda g: g.id) if doc.guides else None
    approved = total = exports = 0
    if doc.status == DocStatus.FAILED:
        stage = "failed"
    elif doc.status in (DocStatus.UPLOADED, DocStatus.PARSING):
        stage = "analyzing"
    elif guide is None:
        stage = "not_started"
    else:
        total = len(guide.summaries)
        approved = sum(s.status == SummaryStatus.APPROVED for s in guide.summaries)
        exports = sum(e.status == ExportStatus.DONE for e in guide.exports)
        if guide.status in (GuideStatus.QUEUED, GuideStatus.SUMMARIZING):
            stage = "summarizing"
        elif guide.status == GuideStatus.REVIEWING:
            stage = "reviewing"
        else:
            stage = "exported" if exports else "approved"
    return DashboardDocument(
        id=doc.id,
        title=doc.title or doc.url or f"문서 {doc.id}",
        vendor_name=doc.vendor.name,
        source_type=doc.source_type,
        page_count=doc.page_count,
        created_at=doc.created_at,
        stage=stage,
        guide_id=guide.id if guide else None,
        target_language=guide.target_language if guide else None,
        approved_sections=approved,
        total_sections=total,
        exports=exports,
        export_files=[
            DashboardExport(id=e.id, format=e.format, doc_version=e.doc_version, created_at=e.created_at)
            for e in sorted(guide.exports, key=lambda e: e.id, reverse=True)
            if e.status == ExportStatus.DONE
        ] if guide else [],
    )
