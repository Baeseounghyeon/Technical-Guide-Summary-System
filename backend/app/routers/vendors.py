from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_vendors, ensure_vendor_access, get_active_user
from ..models import GlossaryTerm, Role, User, Vendor
from ..schemas import GlossaryTermIn, GlossaryTermOut, VendorOut

router = APIRouter(prefix="/api/vendors", tags=["벤더 도메인"])


@router.get("", response_model=list[VendorOut])
def list_vendors(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[Vendor]:
    return accessible_vendors(db, user)


@router.get("/{vendor_id}/glossary", response_model=list[GlossaryTermOut])
def list_glossary(
    vendor_id: int, target_language: str | None = None,
    user: User = Depends(get_active_user), db: Session = Depends(get_db),
) -> list[GlossaryTerm]:
    ensure_vendor_access(db, user, vendor_id)
    query = select(GlossaryTerm).where(GlossaryTerm.vendor_id == vendor_id).order_by(GlossaryTerm.source_term)
    if target_language:
        query = query.where(GlossaryTerm.target_language == target_language)
    return list(db.scalars(query))


@router.put("/{vendor_id}/glossary", response_model=GlossaryTermOut)
def upsert_glossary_term(
    vendor_id: int, body: GlossaryTermIn,
    user: User = Depends(get_active_user), db: Session = Depends(get_db),
) -> GlossaryTerm:
    """용어집은 같은 도메인의 모든 파트너가 공유하므로 관리자 역할만 수정한다."""
    ensure_vendor_access(db, user, vendor_id)
    if user.role not in (Role.PLATFORM_ADMIN, Role.PARTNER_ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "용어집은 관리자만 수정할 수 있습니다.")
    term = db.scalar(
        select(GlossaryTerm).where(
            GlossaryTerm.vendor_id == vendor_id,
            GlossaryTerm.target_language == body.target_language,
            GlossaryTerm.source_term == body.source_term,
        )
    )
    if term is None:
        term = GlossaryTerm(vendor_id=vendor_id, target_language=body.target_language, source_term=body.source_term)
        db.add(term)
    term.target_term = body.target_term
    db.commit()
    return term
