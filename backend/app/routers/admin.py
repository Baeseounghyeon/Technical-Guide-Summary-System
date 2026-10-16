"""플랫폼 관리자 전용: 가입 승인, 파트너사·벤더 도메인 관리."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import accessible_vendors, as_utc, require_platform_admin, user_permissions
from ..models import AccessGrant, GrantStatus, Partner, Role, UsageRecord, User, UserStatus, Vendor, utcnow
from ..schemas import (
    AdminUserOut,
    ApproveIn,
    PartnerIn,
    PartnerOut,
    PartnerVendorsIn,
    ReadGrantBrief,
    UserOut,
    VendorIn,
    VendorOut,
)
from ..services.usage import month_start, partner_quota

router = APIRouter(prefix="/api/admin", tags=["관리자"], dependencies=[Depends(require_platform_admin)])


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    status_filter: str | None = Query(None, alias="status"), db: Session = Depends(get_db)
) -> list[AdminUserOut]:
    """가입자 목록: 소속 파트너사, 할당된 도메인, 유효한 읽기 전용 열람 권한을 함께 돌려준다."""
    query = select(User).order_by(User.created_at.desc())
    if status_filter:
        query = query.where(User.status == status_filter)
    else:
        query = query.where(User.status != UserStatus.DELETED)
    rows = []
    for u in db.scalars(query):
        vendors = accessible_vendors(db, u)
        rows.append(
            AdminUserOut(
                **UserOut.model_validate(u).model_dump(),
                partner_name=u.partner.name if u.partner else None,
                domains=[v.name for v in vendors],
                domain_ids=[v.id for v in vendors],
                custom_domains=bool(u.custom_domains),
                permissions=sorted(user_permissions(db, u)),
                read_grants=_active_read_grants(db, u),
            )
        )
    return rows


def _active_read_grants(db: Session, user: User) -> list[ReadGrantBrief]:
    grants = db.scalars(
        select(AccessGrant).where(
            AccessGrant.user_id == user.id,
            AccessGrant.status == GrantStatus.APPROVED,
            or_(AccessGrant.grant_type.is_(None), AccessGrant.grant_type != "member"),
        )
    )
    now = utcnow()
    return [
        ReadGrantBrief(vendor_name=g.vendor.name, expires_at=g.expires_at)
        for g in grants
        if g.expires_at and as_utc(g.expires_at) > now
    ]


@router.post("/users/{user_id}/approve", response_model=UserOut)
def approve_user(user_id: int, body: ApproveIn, db: Session = Depends(get_db)) -> User:
    user = _get_or_404(db, User, user_id)
    if body.role != Role.PLATFORM_ADMIN and body.partner_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "소속 파트너사를 지정하세요.")
    if body.partner_id is not None:
        _get_or_404(db, Partner, body.partner_id)
    user.partner_id = body.partner_id
    user.role = body.role
    if body.track is not None:
        user.track = body.track
    user.status = UserStatus.ACTIVE
    db.commit()
    return user


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: int, admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)) -> None:
    """가입자 삭제. 문서·이력·게시글의 작성자 기록은 남겨야 하므로 계정을 '삭제됨'으로 바꿔
    로그인과 목록에서 빼고, 같은 메일로 다시 가입할 수 있게 메일 주소를 비워 둔다."""
    user = _get_or_404(db, User, user_id)
    if user.id == admin.id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "자기 자신은 삭제할 수 없습니다.")
    if user.status == UserStatus.DELETED:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 삭제된 가입자입니다.")
    user.status = UserStatus.DELETED
    user.email = f"deleted-{user.id}-{uuid.uuid4().hex[:8]}@deleted.invalid"
    user.phone = None
    db.commit()


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


# ---------- AI 사용량 ----------


class QuotaIn(BaseModel):
    monthly_page_quota: int | None = Field(None, ge=0)  # 비우면 기본값


@router.get("/usage")
def usage_overview(db: Session = Depends(get_db)) -> dict:
    """이번 달 전체 비용·예산과 회사별 사용량."""
    since = month_start()
    rows = db.execute(
        select(
            UsageRecord.partner_id,
            func.sum(UsageRecord.pages),
            func.sum(UsageRecord.input_tokens),
            func.sum(UsageRecord.output_tokens),
            func.sum(UsageRecord.cost_usd),
        )
        .where(UsageRecord.created_at >= since)
        .group_by(UsageRecord.partner_id)
    ).all()
    by_partner = {pid: (int(p or 0), int(i or 0), int(o or 0), float(c or 0)) for pid, p, i, o, c in rows}
    partners = []
    for partner in db.scalars(select(Partner).order_by(Partner.name)):
        pages, tin, tout, cost = by_partner.get(partner.id, (0, 0, 0, 0.0))
        partners.append(
            {
                "id": partner.id,
                "name": partner.name,
                "quota_pages": partner_quota(partner),
                "custom_quota": partner.monthly_page_quota is not None,
                "used_pages": pages,
                "input_tokens": tin,
                "output_tokens": tout,
                "cost_usd": round(cost, 4),
            }
        )
    other = by_partner.get(None, (0, 0, 0, 0.0))
    return {
        "month": since.strftime("%Y-%m"),
        "budget_usd": settings.monthly_budget_usd,
        "cost_usd": round(sum(v[3] for v in by_partner.values()), 4),
        "default_quota_pages": settings.default_monthly_page_quota,
        "daily_regenerate_limit": settings.daily_regenerate_limit,
        "chars_per_page": settings.chars_per_page,
        "llm_provider": settings.llm_provider,
        "partners": partners,
        "unassigned": {"used_pages": other[0], "cost_usd": round(other[3], 4)},  # 플랫폼 관리자 등 소속 없음
    }


@router.put("/partners/{partner_id}/quota")
def set_partner_quota(partner_id: int, body: QuotaIn, db: Session = Depends(get_db)) -> dict:
    partner = db.get(Partner, partner_id)
    if partner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파트너사를 찾을 수 없습니다.")
    partner.monthly_page_quota = body.monthly_page_quota
    db.commit()
    return {"id": partner.id, "quota_pages": partner_quota(partner), "custom_quota": partner.monthly_page_quota is not None}



# ---------- 가입자 정보 수정 · 사용자별 도메인 ----------


class ProfileIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    company_name: str | None = Field(None, max_length=200)
    email: str = Field(min_length=3, max_length=255)
    phone: str | None = Field(None, max_length=50)
    department: str | None = Field(None, max_length=100)


class DomainsIn(BaseModel):
    use_partner_default: bool = False  # 참이면 사용자별 지정을 지우고 소속 파트너사의 도메인을 따른다
    vendor_ids: list[int] = []


@router.put("/users/{user_id}/profile", response_model=UserOut)
def update_profile(user_id: int, body: ProfileIn, db: Session = Depends(get_db)) -> User:
    """가입자 성명·회사명·이메일·전화번호·부서를 고친다 (이메일은 다른 계정과 겹치면 안 됨)."""
    user = _get_or_404(db, User, user_id)
    email = body.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이메일 형식이 올바르지 않습니다.")
    if db.scalar(select(User).where(User.email == email, User.id != user.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "다른 계정이 쓰고 있는 이메일입니다.")
    clean = lambda v: (v or "").strip() or None  # noqa: E731
    user.name = body.name.strip()
    user.email = email
    user.company_name = clean(body.company_name)
    user.phone = clean(body.phone)
    user.department = clean(body.department)
    db.commit()
    return user


@router.put("/users/{user_id}/domains")
def update_user_domains(user_id: int, body: DomainsIn, db: Session = Depends(get_db)) -> dict:
    """사용자별 벤더 도메인 지정. 지정하면 소속 파트너사의 도메인 대신 이 목록만 쓴다."""
    user = _get_or_404(db, User, user_id)
    if body.use_partner_default:
        user.custom_domains = False
        user.vendors = []
    else:
        vendors = list(db.scalars(select(Vendor).where(Vendor.id.in_(body.vendor_ids)))) if body.vendor_ids else []
        if len(vendors) != len(set(body.vendor_ids)):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "없는 벤더 도메인이 포함되어 있습니다.")
        user.custom_domains = True
        user.vendors = vendors
    db.commit()
    return {"custom_domains": bool(user.custom_domains), "domains": [v.name for v in accessible_vendors(db, user)]}
