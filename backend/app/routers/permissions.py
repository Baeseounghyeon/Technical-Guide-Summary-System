"""권한 승인 요청: 업무 구분 밖의 권한을 관리자에게 신청하고, 관리자가 승인·반려한다.

예) 영업 사용자가 '가이드 등록·요약' 권한을 신청 → 승인되면 엔지니어처럼 가이드를 등록·요약할 수 있다.
"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import PERMISSION_LABELS, get_active_user, require_platform_admin, user_permissions
from ..models import PermissionRequest, User, utcnow
from ..schemas import UTCDateTime

router = APIRouter(prefix="/api", tags=["권한 승인 요청"])

Scope = Literal["guide", "spec", "quote", "price_list", "purchase", "brochure"]


class PermissionRequestIn(BaseModel):
    scopes: list[Scope] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=5000)
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    company: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=50)


class PermissionDecisionIn(BaseModel):
    approve: bool
    note: str | None = None


class PermissionRequestOut(BaseModel):
    id: int
    user_id: int
    user_track: str | None
    scopes: list[str]
    scope_labels: list[str]
    reason: str
    name: str | None
    email: str | None
    company: str | None
    phone: str | None
    status: str
    decided_by_name: str | None
    decided_at: UTCDateTime | None
    decision_note: str | None
    created_at: UTCDateTime


def _out(db: Session, r: PermissionRequest) -> PermissionRequestOut:
    decider = db.get(User, r.decided_by) if r.decided_by else None
    return PermissionRequestOut(
        id=r.id,
        user_id=r.user_id,
        user_track=r.user.track,
        scopes=list(r.scopes or []),
        scope_labels=[PERMISSION_LABELS.get(s, s) for s in r.scopes or []],
        reason=r.reason,
        name=r.name,
        email=r.email,
        company=r.company,
        phone=r.phone,
        status=r.status,
        decided_by_name=decider.name if decider else None,
        decided_at=r.decided_at,
        decision_note=r.decision_note,
        created_at=r.created_at,
    )


@router.post("/permission-requests", response_model=PermissionRequestOut, status_code=status.HTTP_201_CREATED)
def create_request(body: PermissionRequestIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> PermissionRequestOut:
    have = user_permissions(db, user)
    wanted = sorted(set(body.scopes) - have)
    if not wanted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이미 가진 권한입니다.")
    pending = db.scalar(select(PermissionRequest).where(PermissionRequest.user_id == user.id, PermissionRequest.status == "pending"))
    if pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "승인 대기 중인 권한 요청이 있습니다. 처리된 뒤에 다시 신청하세요.")
    clean = lambda v: (v or "").strip() or None  # noqa: E731
    request = PermissionRequest(
        user_id=user.id,
        scopes=wanted,
        reason=body.reason.strip(),
        name=body.name.strip(),
        email=body.email.strip(),
        company=clean(body.company),
        phone=clean(body.phone),
    )
    db.add(request)
    db.commit()
    return _out(db, request)


@router.get("/permission-requests/mine", response_model=list[PermissionRequestOut])
def my_requests(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[PermissionRequestOut]:
    rows = db.scalars(select(PermissionRequest).where(PermissionRequest.user_id == user.id).order_by(PermissionRequest.id.desc()))
    return [_out(db, r) for r in rows]


@router.get("/admin/permission-requests", response_model=list[PermissionRequestOut], dependencies=[Depends(require_platform_admin)])
def admin_list(status_filter: str | None = Query(None, alias="status"), db: Session = Depends(get_db)) -> list[PermissionRequestOut]:
    query = select(PermissionRequest).order_by(PermissionRequest.id.desc())
    if status_filter:
        query = query.where(PermissionRequest.status == status_filter)
    return [_out(db, r) for r in db.scalars(query)]


@router.post("/admin/permission-requests/{request_id}/decision", response_model=PermissionRequestOut)
def admin_decide(
    request_id: int, body: PermissionDecisionIn, admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> PermissionRequestOut:
    request = db.get(PermissionRequest, request_id)
    if request is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "권한 요청을 찾을 수 없습니다.")
    if request.status != "pending" and body.approve:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 처리된 요청입니다.")
    # 반려는 대기 중인 요청을 거절하거나, 승인했던 권한을 회수할 때 쓴다.
    if body.approve:
        request.status = "approved"
    else:
        request.status = "revoked" if request.status == "approved" else "rejected"
    request.decided_by, request.decided_at = admin.id, utcnow()
    request.decision_note = (body.note or "").strip() or None
    db.commit()
    return _out(db, request)
