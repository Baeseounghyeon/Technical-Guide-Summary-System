"""같은 벤더 도메인 파트너사 간 가이드 공유: 목록 → 다운로드 요청 → 소유 파트너사 승인 → 다운로드. 상단 알림 포함."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_vendors, get_active_user, is_admin
from ..models import (
    DownloadRequest,
    Export,
    ExportStatus,
    GrantStatus,
    Guide,
    GuideStatus,
    Notification,
    Partner,
    Role,
    SourceDocument,
    User,
    utcnow,
)
from ..schemas import (
    DownloadDecisionIn,
    DownloadRequestIn,
    DownloadRequestOut,
    NotificationList,
    NotificationOut,
    SharedExportOut,
    SharedGuideOut,
)

router = APIRouter(prefix="/api", tags=["가이드 공유 · 알림"])


# ---------- 공유 가이드 목록 ----------


@router.get("/shared-guides", response_model=list[SharedGuideOut])
def list_shared_guides(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[SharedGuideOut]:
    """내 파트너사 도메인 안에서 다른 파트너사가 최종 문서까지 만든 가이드 (파일 자체는 승인 후에만 받을 수 있다)."""
    if user.partner_id is None:
        return []
    vendor_ids = [v.id for v in accessible_vendors(db, user)]
    guides = db.scalars(
        select(Guide)
        .join(SourceDocument)
        .where(
            Guide.status == GuideStatus.APPROVED,
            SourceDocument.vendor_id.in_(vendor_ids),
            SourceDocument.partner_id.is_not(None),
            SourceDocument.partner_id != user.partner_id,
        )
        .order_by(Guide.id.desc())
    )
    result = []
    for g in guides:
        done = [e for e in g.exports if e.status == ExportStatus.DONE]
        if not done:
            continue
        req = _latest_request(db, g.id, user.partner_id)
        result.append(
            SharedGuideOut(
                guide_id=g.id,
                title=g.document.title or f"문서 {g.document_id}",
                vendor_name=g.document.vendor.name,
                owner_partner_name=db.get(Partner, g.document.partner_id).name,
                target_language=g.target_language,
                formats=sorted({e.format for e in done}),
                updated_at=max(e.created_at for e in done),
                request_id=req.id if req else None,
                request_status=req.status if req else "none",
                decision_note=req.decision_note if req else None,
            )
        )
    return result


@router.get("/shared-guides/{guide_id}/exports", response_model=list[SharedExportOut])
def shared_exports(guide_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[Export]:
    guide = db.get(Guide, guide_id)
    if guide is None or not can_download_shared(db, user, guide):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "소유 파트너사의 다운로드 승인이 필요합니다.")
    return [e for e in guide.exports if e.status == ExportStatus.DONE]


# ---------- 다운로드 요청 / 승인 ----------


@router.post("/shared-guides/{guide_id}/requests", response_model=DownloadRequestOut, status_code=status.HTTP_201_CREATED)
def request_download(
    guide_id: int, body: DownloadRequestIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> DownloadRequestOut:
    guide = db.get(Guide, guide_id)
    doc = guide.document if guide else None
    if (
        guide is None
        or user.partner_id is None
        or doc.partner_id is None
        or doc.partner_id == user.partner_id
        or doc.vendor_id not in {v.id for v in accessible_vendors(db, user)}
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "요청할 수 있는 가이드가 아닙니다.")
    latest = _latest_request(db, guide.id, user.partner_id)
    if latest and latest.status in (GrantStatus.PENDING, GrantStatus.APPROVED):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 요청했거나 승인된 가이드입니다.")

    req = DownloadRequest(
        guide_id=guide.id,
        requester_id=user.id,
        requester_partner_id=user.partner_id,
        owner_partner_id=doc.partner_id,
        message=(body.message or "").strip() or None,
    )
    db.add(req)
    db.flush()
    title = doc.title or f"문서 {doc.id}"
    for approver in _approvers(db, req):
        db.add(
            Notification(
                user_id=approver.id,
                kind="download_request",
                title=f"{user.partner.name} {user.name}님이 가이드 다운로드를 요청했습니다",
                body=f"{title}" + (f"\n요청 사유: {req.message}" if req.message else ""),
                link="/shared?tab=incoming",
                related_id=req.id,
            )
        )
    db.commit()
    return _request_out(db, user, req)


@router.get("/download-requests/incoming", response_model=list[DownloadRequestOut])
def incoming_requests(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[DownloadRequestOut]:
    """내 파트너사 가이드에 들어온 요청 (승인 권한이 없으면 빈 목록)."""
    query = select(DownloadRequest).order_by(DownloadRequest.id.desc())
    if not is_admin(user):
        if user.partner_id is None:
            return []
        query = query.where(DownloadRequest.owner_partner_id == user.partner_id)
    return [_request_out(db, user, r) for r in db.scalars(query) if _can_decide(user, r)]


@router.get("/download-requests/outgoing", response_model=list[DownloadRequestOut])
def outgoing_requests(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[DownloadRequestOut]:
    if user.partner_id is None:
        return []
    query = select(DownloadRequest).where(DownloadRequest.requester_partner_id == user.partner_id).order_by(DownloadRequest.id.desc())
    return [_request_out(db, user, r) for r in db.scalars(query)]


@router.post("/download-requests/{request_id}/decision", response_model=DownloadRequestOut)
def decide_request(
    request_id: int, body: DownloadDecisionIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> DownloadRequestOut:
    req = db.get(DownloadRequest, request_id)
    if req is None or not _can_decide(user, req):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "처리할 수 있는 요청이 아닙니다.")
    if req.status != GrantStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 처리된 요청입니다.")
    req.status = GrantStatus.APPROVED if body.approve else GrantStatus.REJECTED
    req.decided_by, req.decided_at = user.id, utcnow()
    req.decision_note = (body.note or "").strip() or None

    # 같은 요청으로 다른 승인권자에게 간 알림은 읽음 처리한다.
    for n in db.scalars(select(Notification).where(Notification.kind == "download_request", Notification.related_id == req.id)):
        n.read_at = n.read_at or utcnow()
    title = req.guide.document.title or f"문서 {req.guide.document_id}"
    result = "승인" if body.approve else "거절"
    db.add(
        Notification(
            user_id=req.requester_id,
            kind="download_decision",
            title=f"{req.owner_partner.name}이(가) 다운로드 요청을 {result}했습니다",
            body=title + (f"\n메모: {req.decision_note}" if req.decision_note else ""),
            link="/shared",
            related_id=req.id,
        )
    )
    db.commit()
    return _request_out(db, user, req)


# ---------- 알림 ----------


@router.get("/notifications", response_model=NotificationList)
def list_notifications(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> NotificationList:
    items = list(
        db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(30))
    )
    unread = sum(1 for n in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))))
    out = []
    for n in items:
        item = NotificationOut.model_validate(n)
        if n.kind == "download_request" and n.related_id:
            req = db.get(DownloadRequest, n.related_id)
            item.actionable = bool(req and req.status == GrantStatus.PENDING and _can_decide(user, req))
        out.append(item)
    return NotificationList(unread=unread, items=out)


@router.post("/notifications/{notification_id}/read", status_code=status.HTTP_204_NO_CONTENT)
def read_notification(notification_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> None:
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "알림을 찾을 수 없습니다.")
    n.read_at = n.read_at or utcnow()
    db.commit()


@router.post("/notifications/read-all", status_code=status.HTTP_204_NO_CONTENT)
def read_all(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> None:
    for n in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))):
        n.read_at = utcnow()
    db.commit()


# ---------- 공통 ----------


def can_download_shared(db: Session, user: User, guide: Guide) -> bool:
    """다른 파트너사 가이드: 내 파트너사의 요청이 승인되었으면 받을 수 있다."""
    if user.partner_id is None:
        return False
    req = _latest_request(db, guide.id, user.partner_id)
    return bool(req and req.status == GrantStatus.APPROVED)


def _latest_request(db: Session, guide_id: int, partner_id: int) -> DownloadRequest | None:
    return db.scalar(
        select(DownloadRequest)
        .where(DownloadRequest.guide_id == guide_id, DownloadRequest.requester_partner_id == partner_id)
        .order_by(DownloadRequest.id.desc())
        .limit(1)
    )


def _approvers(db: Session, req: DownloadRequest) -> list[User]:
    """소유 파트너사의 파트너 관리자 + 그 문서를 올린 사람."""
    users = {
        u.id: u
        for u in db.scalars(select(User).where(User.partner_id == req.owner_partner_id, User.role == Role.PARTNER_ADMIN))
    }
    uploader = db.get(User, req.guide.document.uploaded_by)
    if uploader and uploader.partner_id == req.owner_partner_id:
        users[uploader.id] = uploader
    return list(users.values())


def _can_decide(user: User, req: DownloadRequest) -> bool:
    if is_admin(user):
        return True
    if user.partner_id != req.owner_partner_id:
        return False
    return user.role == Role.PARTNER_ADMIN or req.guide.document.uploaded_by == user.id


def _request_out(db: Session, user: User, r: DownloadRequest) -> DownloadRequestOut:
    decider = db.get(User, r.decided_by) if r.decided_by else None
    return DownloadRequestOut(
        id=r.id,
        guide_id=r.guide_id,
        guide_title=r.guide.document.title or f"문서 {r.guide.document_id}",
        vendor_name=r.guide.document.vendor.name,
        requester_name=r.requester.name,
        requester_email=r.requester.email,
        requester_partner_name=r.requester_partner.name,
        owner_partner_name=r.owner_partner.name,
        message=r.message,
        status=r.status,
        decided_by_name=decider.name if decider else None,
        decided_at=r.decided_at,
        decision_note=r.decision_note,
        created_at=r.created_at,
        can_decide=r.status == GrantStatus.PENDING and _can_decide(user, r),
    )
