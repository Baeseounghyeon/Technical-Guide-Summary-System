"""인증과 도메인 접근 권한 검사.

접근 규칙 (docs/PRODUCT_PLAN.md 3절)
- 플랫폼 관리자는 모든 데이터에 접근한다.
- 그 외 사용자는 자기 파트너사가 지원하는 벤더 도메인 안에서, 자기 파트너사 문서만 본다.
"""

from datetime import datetime, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import (
    AccessGrant,
    GrantStatus,
    Guide,
    Role,
    SourceDocument,
    User,
    UserStatus,
    Vendor,
    utcnow,
)
from .security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    user_id = decode_access_token(token)
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다.")
    return user


def get_active_user(user: User = Depends(get_current_user)) -> User:
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "승인된 계정만 사용할 수 있습니다.")
    return user


def require_platform_admin(user: User = Depends(get_active_user)) -> User:
    if user.role != Role.PLATFORM_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "플랫폼 관리자 권한이 필요합니다.")
    return user


def is_admin(user: User) -> bool:
    return user.role == Role.PLATFORM_ADMIN


def accessible_vendors(db: Session, user: User) -> list[Vendor]:
    if is_admin(user):
        return list(db.scalars(select(Vendor).order_by(Vendor.name)))
    return sorted(user.partner.vendors, key=lambda v: v.name) if user.partner else []


def ensure_vendor_access(db: Session, user: User, vendor_id: int) -> None:
    if vendor_id not in {v.id for v in accessible_vendors(db, user)}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "이 벤더 도메인에 접근할 권한이 없습니다.")


def get_document_for_user(db: Session, user: User, document_id: int) -> SourceDocument:
    doc = db.get(SourceDocument, document_id)
    # 다른 파트너사·도메인 문서는 존재 여부도 드러내지 않는다.
    if doc is None or not _can_see_document(db, user, doc):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "문서를 찾을 수 없습니다.")
    return doc


def get_guide_for_user(db: Session, user: User, guide_id: int) -> Guide:
    guide = db.get(Guide, guide_id)
    if guide is None or not _can_see_document(db, user, guide.document):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "가이드를 찾을 수 없습니다.")
    return guide


def _can_see_document(db: Session, user: User, doc: SourceDocument) -> bool:
    if is_admin(user):
        return True
    return doc.partner_id == user.partner_id and doc.vendor_id in {v.id for v in accessible_vendors(db, user)}


# ---------- 커뮤니티 접근 (3단계) ----------
# member : 자기 파트너사가 지원하는 벤더 도메인 → 읽기·쓰기
# granted: 관리자가 기간을 정해 열람을 승인한 다른 도메인 → 읽기만
# none   : 그 외 → 접근 불가 (열람 신청만 가능)


def active_grant(db: Session, user: User, vendor_id: int) -> AccessGrant | None:
    grants = db.scalars(
        select(AccessGrant).where(
            AccessGrant.user_id == user.id,
            AccessGrant.vendor_id == vendor_id,
            AccessGrant.status == GrantStatus.APPROVED,
        )
    )
    now = utcnow()
    return next((g for g in grants if g.expires_at and as_utc(g.expires_at) > now), None)


def domain_access(db: Session, user: User, vendor_id: int) -> str:
    if vendor_id in {v.id for v in accessible_vendors(db, user)}:
        return "member"
    return "granted" if active_grant(db, user, vendor_id) else "none"


def require_domain_read(db: Session, user: User, vendor_id: int) -> str:
    access = domain_access(db, user, vendor_id)
    if access == "none":
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "이 도메인 커뮤니티를 볼 권한이 없습니다. 열람 신청 후 관리자 승인을 받으세요."
        )
    return access


def require_domain_write(db: Session, user: User, vendor_id: int) -> None:
    if domain_access(db, user, vendor_id) != "member":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "열람 승인된 도메인에서는 읽기만 할 수 있습니다.")


def as_utc(value: datetime) -> datetime:
    """SQLite 는 시간대를 저장하지 않으므로 UTC 로 간주해 시간대를 붙인다."""
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
