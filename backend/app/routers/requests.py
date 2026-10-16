"""요약 요청 목록: 내 요청 사항(내가 요약을 요청한 가이드) / 조직 요청 가이드(같은 회사 사람들이 요청한 가이드)."""

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_vendors, get_active_user, is_admin
from ..models import ExportStatus, Guide, SourceDocument, SummaryStatus, User
from ..schemas import UTCDateTime

router = APIRouter(prefix="/api", tags=["요약 요청"])


class ExportBrief(BaseModel):
    id: int
    format: str
    doc_version: str


class RequestOut(BaseModel):
    guide_id: int
    document_id: int
    document_title: str | None
    vendor_name: str
    partner_name: str | None
    target_language: str
    status: str
    approved: int
    total: int
    requested_by_name: str | None
    created_at: UTCDateTime
    exports: list[ExportBrief]  # 생성 완료된 최종 문서 (같은 조직이면 내려받기 가능)


def _out(guide: Guide, names: dict[int, str]) -> RequestOut:
    doc = guide.document
    summaries = guide.summaries
    return RequestOut(
        guide_id=guide.id,
        document_id=doc.id,
        document_title=doc.title or doc.url,
        vendor_name=doc.vendor.name,
        partner_name=doc.partner.name if doc.partner else None,
        target_language=guide.target_language,
        status=guide.status,
        approved=sum(1 for s in summaries if s.status == SummaryStatus.APPROVED),
        total=len(summaries),
        requested_by_name=names.get(guide.created_by),
        created_at=guide.created_at,
        exports=[
            ExportBrief(id=e.id, format=e.format, doc_version=e.doc_version)
            for e in sorted(guide.exports, key=lambda e: e.id, reverse=True)
            if e.status == ExportStatus.DONE
        ],
    )


def _names(db: Session, guides: list[Guide]) -> dict[int, str]:
    ids = {g.created_by for g in guides}
    return {u.id: u.name for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}


def _sorted(guides) -> list[Guide]:
    return sorted(guides, key=lambda g: g.created_at or datetime.min, reverse=True)


@router.get("/my-requests", response_model=list[RequestOut])
def my_requests(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[RequestOut]:
    """내가 요약을 요청한 가이드."""
    guides = _sorted(g for g in db.scalars(select(Guide).where(Guide.created_by == user.id)) if g.document.deleted_at is None)
    names = _names(db, guides)
    return [_out(g, names) for g in guides]


@router.get("/org-guides", response_model=list[RequestOut])
def org_guides(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[RequestOut]:
    """같은 조직(파트너사)에서 요약을 요청한 가이드. 같은 조직이면 최종 문서를 내려받을 수 있다."""
    query = select(Guide).join(SourceDocument, Guide.document_id == SourceDocument.id).where(SourceDocument.deleted_at.is_(None))
    if not is_admin(user):
        vendor_ids = [v.id for v in accessible_vendors(db, user)]
        query = query.where(SourceDocument.partner_id == user.partner_id, SourceDocument.vendor_id.in_(vendor_ids))
    guides = _sorted(db.scalars(query))
    names = _names(db, guides)
    return [_out(g, names) for g in guides]
