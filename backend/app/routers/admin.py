"""플랫폼 관리자 전용: 가입 승인, 파트너사·벤더 도메인 관리."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_platform_admin
from ..models import Partner, Role, User, UserStatus, Vendor
from ..schemas import ApproveIn, PartnerIn, PartnerOut, PartnerVendorsIn, UserOut, VendorIn, VendorOut

router = APIRouter(prefix="/api/admin", tags=["관리자"], dependencies=[Depends(require_platform_admin)])


@router.get("/users", response_model=list[UserOut])
def list_users(
    status_filter: str | None = Query(None, alias="status"), db: Session = Depends(get_db)
) -> list[User]:
    query = select(User).order_by(User.created_at.desc())
    if status_filter:
        query = query.where(User.status == status_filter)
    return list(db.scalars(query))


@router.post("/users/{user_id}/approve", response_model=UserOut)
def approve_user(user_id: int, body: ApproveIn, db: Session = Depends(get_db)) -> User:
    user = _get_or_404(db, User, user_id)
    if body.role != Role.PLATFORM_ADMIN and body.partner_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "소속 파트너사를 지정하세요.")
    if body.partner_id is not None:
        _get_or_404(db, Partner, body.partner_id)
    user.partner_id = body.partner_id
    user.role = body.role
    user.status = UserStatus.ACTIVE
    db.commit()
    return user


@router.post("/users/{user_id}/suspend", response_model=UserOut)
def suspend_user(user_id: int, db: Session = Depends(get_db)) -> User:
    user = _get_or_404(db, User, user_id)
    user.status = UserStatus.SUSPENDED
    db.commit()
    return user


@router.get("/partners", response_model=list[PartnerOut])
def list_partners(db: Session = Depends(get_db)) -> list[Partner]:
    return list(db.scalars(select(Partner).order_by(Partner.name)))


@router.post("/partners", response_model=PartnerOut, status_code=status.HTTP_201_CREATED)
def create_partner(body: PartnerIn, db: Session = Depends(get_db)) -> Partner:
    if db.scalar(select(Partner).where(Partner.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "같은 이름의 파트너사가 있습니다.")
    partner = Partner(name=body.name)
    db.add(partner)
    db.commit()
    return partner


@router.put("/partners/{partner_id}/vendors", response_model=PartnerOut)
def set_partner_vendors(partner_id: int, body: PartnerVendorsIn, db: Session = Depends(get_db)) -> Partner:
    """파트너사가 지원하는 벤더 도메인을 지정한다."""
    partner = _get_or_404(db, Partner, partner_id)
    vendors = list(db.scalars(select(Vendor).where(Vendor.id.in_(body.vendor_ids))))
    if len(vendors) != len(set(body.vendor_ids)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "존재하지 않는 벤더가 포함되어 있습니다.")
    partner.vendors = vendors
    db.commit()
    return partner


@router.post("/vendors", response_model=VendorOut, status_code=status.HTTP_201_CREATED)
def create_vendor(body: VendorIn, db: Session = Depends(get_db)) -> Vendor:
    if db.scalar(select(Vendor).where(Vendor.name == body.name)):
        raise HTTPException(status.HTTP_409_CONFLICT, "같은 이름의 벤더가 있습니다.")
    vendor = Vendor(name=body.name, description=body.description)
    db.add(vendor)
    db.commit()
    return vendor


def _get_or_404(db: Session, model, obj_id: int):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "대상을 찾을 수 없습니다.")
    return obj
