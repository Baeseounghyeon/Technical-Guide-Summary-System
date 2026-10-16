"""3단계: 벤더 도메인별 커뮤니티 (이슈 처리 경험 공유, 온라인 세션 일정)와 타 도메인 열람 승인."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import (
    active_grant,
    as_utc,
    domain_access,
    get_active_user,
    is_admin,
    require_domain_read,
    require_domain_write,
    require_platform_admin,
)
from ..models import (
    AccessGrant,
    Comment,
    EventAttendee,
    GrantStatus,
    Post,
    PostStatus,
    SessionEvent,
    User,
    Vendor,
    utcnow,
)
from ..schemas import (
    AccessDecisionIn,
    AccessGrantOut,
    AccessRequestIn,
    Author,
    CommentIn,
    CommentOut,
    DomainOut,
    EventIn,
    EventOut,
    PostDetail,
    PostIn,
    PostStatusIn,
    PostSummary,
)

router = APIRouter(prefix="/api", tags=["커뮤니티"])


# ---------- 도메인 목록 ----------


@router.get("/community/domains", response_model=list[DomainOut])
def list_domains(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[DomainOut]:
    """모든 벤더 도메인과 내 접근 상태. 접근할 수 없는 도메인은 이름만 보이고 열람 신청할 수 있다."""
    pending = set(
        db.scalars(
            select(AccessGrant.vendor_id).where(AccessGrant.user_id == user.id, AccessGrant.status == GrantStatus.PENDING)
        )
    )
    now = utcnow()
    result = []
    for vendor in db.scalars(select(Vendor).order_by(Vendor.name)):
        access = domain_access(db, user, vendor.id)
        grant = active_grant(db, user, vendor.id) if access == "granted" else None
        out = DomainOut(
            vendor_id=vendor.id,
            vendor_name=vendor.name,
            access=access,
            grant_expires_at=grant.expires_at if grant else None,
            pending_request=vendor.id in pending,
        )
        if access != "none":
            out.post_count = db.scalar(select(func.count()).select_from(Post).where(Post.vendor_id == vendor.id)) or 0
            events = db.scalars(select(SessionEvent).where(SessionEvent.vendor_id == vendor.id))
            out.upcoming_events = sum(as_utc(e.ends_at or e.starts_at) >= now for e in events)
        result.append(out)
    return result


# ---------- 이슈 공유 게시판 ----------


@router.get("/community/{vendor_id}/posts", response_model=list[PostSummary])
def list_posts(
    vendor_id: int,
    q: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    tag: str | None = None,
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> list[PostSummary]:
    require_domain_read(db, user, vendor_id)
    query = select(Post).where(Post.vendor_id == vendor_id).order_by(Post.created_at.desc())
    if status_filter:
        query = query.where(Post.status == status_filter)
    if q:
        like = f"%{q}%"
        query = query.where(or_(Post.title.ilike(like), Post.body.ilike(like), Post.product.ilike(like), Post.version.ilike(like)))
    posts = list(db.scalars(query))
    if tag:
        posts = [p for p in posts if tag in (p.tags or [])]
    return [_post_summary(p) for p in posts]


@router.post("/community/{vendor_id}/posts", response_model=PostDetail, status_code=status.HTTP_201_CREATED)
def create_post(vendor_id: int, body: PostIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> PostDetail:
    if db.get(Vendor, vendor_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "벤더 도메인을 찾을 수 없습니다.")
    require_domain_write(db, user, vendor_id)
    post = Post(vendor_id=vendor_id, author_id=user.id, **_clean_post(body))
    db.add(post)
    db.commit()
    return _post_detail(db, user, post)


@router.get("/community/posts/{post_id}", response_model=PostDetail)
def get_post(post_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> PostDetail:
    return _post_detail(db, user, _readable_post(db, user, post_id))


@router.put("/community/posts/{post_id}", response_model=PostDetail)
def update_post(post_id: int, body: PostIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> PostDetail:
    post = _editable_post(db, user, post_id)
    for key, value in _clean_post(body).items():
        setattr(post, key, value)
    db.commit()
    return _post_detail(db, user, post)


@router.delete("/community/posts/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_post(post_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> None:
    db.delete(_editable_post(db, user, post_id))
    db.commit()


@router.patch("/community/posts/{post_id}/status", response_model=PostDetail)
def set_post_status(
    post_id: int, body: PostStatusIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> PostDetail:
    """해결 표시. 해결에 도움이 된 댓글을 함께 지정할 수 있다."""
    post = _editable_post(db, user, post_id)
    if body.solution_comment_id is not None and body.solution_comment_id not in {c.id for c in post.comments}:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이 글의 댓글이 아닙니다.")
    post.status = body.status
    post.solution_comment_id = body.solution_comment_id if body.status == PostStatus.RESOLVED else None
    db.commit()
    return _post_detail(db, user, post)


@router.post("/community/posts/{post_id}/comments", response_model=PostDetail, status_code=status.HTTP_201_CREATED)
def add_comment(post_id: int, body: CommentIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> PostDetail:
    post = _readable_post(db, user, post_id)
    require_domain_write(db, user, post.vendor_id)
    post.comments.append(Comment(author_id=user.id, body=body.body.strip()))
    db.commit()
    return _post_detail(db, user, post)


@router.delete("/community/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_comment(comment_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> None:
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "댓글을 찾을 수 없습니다.")
    post = _readable_post(db, user, comment.post_id)
    if comment.author_id != user.id and not is_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "본인 댓글만 지울 수 있습니다.")
    if post.solution_comment_id == comment.id:
        post.solution_comment_id = None
    db.delete(comment)
    db.commit()


# ---------- 온라인 세션 일정 ----------


@router.get("/community/{vendor_id}/events", response_model=list[EventOut])
def list_events(
    vendor_id: int,
    scope: str = Query("upcoming", pattern="^(upcoming|past)$"),
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> list[EventOut]:
    access = require_domain_read(db, user, vendor_id)
    now = utcnow()
    events = list(db.scalars(select(SessionEvent).where(SessionEvent.vendor_id == vendor_id)))
    if scope == "upcoming":
        events = sorted((e for e in events if as_utc(e.ends_at or e.starts_at) >= now), key=lambda e: as_utc(e.starts_at))
    else:
        events = sorted((e for e in events if as_utc(e.ends_at or e.starts_at) < now), key=lambda e: as_utc(e.starts_at), reverse=True)
    return [_event_out(user, e, access) for e in events]


@router.post("/community/{vendor_id}/events", response_model=EventOut, status_code=status.HTTP_201_CREATED)
def create_event(vendor_id: int, body: EventIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> EventOut:
    if db.get(Vendor, vendor_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "벤더 도메인을 찾을 수 없습니다.")
    require_domain_write(db, user, vendor_id)
    event = SessionEvent(vendor_id=vendor_id, organizer_id=user.id, **_clean_event(body))
    db.add(event)
    db.commit()
    return _event_out(user, event, "member")


@router.put("/community/events/{event_id}", response_model=EventOut)
def update_event(event_id: int, body: EventIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> EventOut:
    event = _editable_event(db, user, event_id)
    for key, value in _clean_event(body).items():
        setattr(event, key, value)
    db.commit()
    return _event_out(user, event, "member")


@router.delete("/community/events/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_event(event_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> None:
    db.delete(_editable_event(db, user, event_id))
    db.commit()


@router.post("/community/events/{event_id}/rsvp", response_model=EventOut)
def rsvp(event_id: int, attending: bool = True, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> EventOut:
    """참석 표시. 열람 승인 사용자도 세션에는 참석할 수 있다."""
    event = db.get(SessionEvent, event_id)
    if event is None or domain_access(db, user, event.vendor_id) == "none":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "일정을 찾을 수 없습니다.")
    existing = db.get(EventAttendee, (event.id, user.id))
    if attending and existing is None:
        event.attendees.append(EventAttendee(user_id=user.id))
    elif not attending and existing is not None:
        event.attendees.remove(existing)
    db.commit()
    return _event_out(user, event, domain_access(db, user, event.vendor_id))


# ---------- 타 도메인 열람 신청 / 관리자 승인 ----------


@router.post("/community/{vendor_id}/access-requests", response_model=AccessGrantOut, status_code=status.HTTP_201_CREATED)
def request_access(
    vendor_id: int, body: AccessRequestIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> AccessGrantOut:
    if db.get(Vendor, vendor_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "벤더 도메인을 찾을 수 없습니다.")
    access = domain_access(db, user, vendor_id)
    if access == "member":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이미 소속된 도메인입니다.")
    if access == "granted":
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 열람 승인을 받은 도메인입니다.")
    if db.scalar(
        select(AccessGrant).where(
            AccessGrant.user_id == user.id, AccessGrant.vendor_id == vendor_id, AccessGrant.status == GrantStatus.PENDING
        )
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 승인 대기 중인 신청이 있습니다.")
    clean = lambda v: (v or "").strip() or None  # noqa: E731
    grant = AccessGrant(
        user_id=user.id,
        vendor_id=vendor_id,
        reason=body.reason.strip(),
        requested_days=body.days,
        request_date=body.request_date,
        requester_name=clean(body.requester_name) or user.name,
        requester_email=clean(body.requester_email) or user.email,
        requester_company=clean(body.requester_company) or user.company_name,
    )
    db.add(grant)
    db.commit()
    return _grant_out(db, grant)


@router.get("/community/access-requests/mine", response_model=list[AccessGrantOut])
def my_requests(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[AccessGrantOut]:
    grants = db.scalars(select(AccessGrant).where(AccessGrant.user_id == user.id).order_by(AccessGrant.id.desc()))
    return [_grant_out(db, g) for g in grants]


@router.get("/admin/access-requests", response_model=list[AccessGrantOut], dependencies=[Depends(require_platform_admin)])
def admin_list_requests(status_filter: str | None = Query(None, alias="status"), db: Session = Depends(get_db)) -> list[AccessGrantOut]:
    query = select(AccessGrant).order_by(AccessGrant.id.desc())
    if status_filter:
        query = query.where(AccessGrant.status == status_filter)
    return [_grant_out(db, g) for g in db.scalars(query)]


@router.post("/admin/access-requests/{grant_id}/decision", response_model=AccessGrantOut)
def admin_decide(
    grant_id: int, body: AccessDecisionIn, admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)
) -> AccessGrantOut:
    grant = _grant_or_404(db, grant_id)
    if grant.status != GrantStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 처리된 신청입니다.")
    now = utcnow()
    if body.approve and body.grant_type == "member":
        # 정식 소속: 신청자의 파트너사에 도메인을 연결한다 → 그 파트너사 엔지니어 모두 읽기·쓰기·문서 업로드 가능
        partner = grant.user.partner
        if partner is None:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "신청자에게 소속 파트너사가 없어 정식 소속을 부여할 수 없습니다.")
        if grant.vendor not in partner.vendors:
            partner.vendors.append(grant.vendor)
        grant.expires_at = None
    elif body.approve:
        grant.expires_at = now + timedelta(days=body.days or grant.requested_days)
    grant.status = GrantStatus.APPROVED if body.approve else GrantStatus.REJECTED
    grant.grant_type = body.grant_type if body.approve else None
    grant.decided_by, grant.decided_at, grant.decision_note = admin.id, now, (body.note or "").strip() or None
    db.commit()
    return _grant_out(db, grant)


@router.post("/admin/access-requests/{grant_id}/revoke", response_model=AccessGrantOut)
def admin_revoke(grant_id: int, admin: User = Depends(require_platform_admin), db: Session = Depends(get_db)) -> AccessGrantOut:
    grant = _grant_or_404(db, grant_id)
    if grant.status != GrantStatus.APPROVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "승인된 열람만 회수할 수 있습니다.")
    if grant.grant_type == "member" and grant.user.partner and grant.vendor in grant.user.partner.vendors:
        grant.user.partner.vendors.remove(grant.vendor)  # 정식 소속 회수: 파트너사-도메인 연결을 끊는다
    grant.status = GrantStatus.REVOKED
    grant.decided_by, grant.decided_at = admin.id, utcnow()
    db.commit()
    return _grant_out(db, grant)


# ---------- 내부 함수 ----------


def _author(user: User) -> Author:
    return Author(id=user.id, name=user.name, partner_name=user.partner.name if user.partner else None)


def _clean_post(body: PostIn) -> dict:
    tags = []
    for t in body.tags:
        t = t.strip().lstrip("#")
        if t and t not in tags:
            tags.append(t[:50])
    return {
        "title": body.title.strip(),
        "body": body.body.strip(),
        "product": (body.product or "").strip() or None,
        "version": (body.version or "").strip() or None,
        "tags": tags,
    }


def _readable_post(db: Session, user: User, post_id: int) -> Post:
    post = db.get(Post, post_id)
    if post is None or domain_access(db, user, post.vendor_id) == "none":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "글을 찾을 수 없습니다.")
    return post


def _editable_post(db: Session, user: User, post_id: int) -> Post:
    post = _readable_post(db, user, post_id)
    if post.author_id != user.id and not is_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "작성자만 수정할 수 있습니다.")
    return post


def _post_summary(post: Post) -> PostSummary:
    return PostSummary(
        id=post.id,
        vendor_id=post.vendor_id,
        title=post.title,
        product=post.product,
        version=post.version,
        tags=post.tags or [],
        status=post.status,
        author=_author(post.author),
        comment_count=len(post.comments),
        created_at=post.created_at,
    )


def _post_detail(db: Session, user: User, post: Post) -> PostDetail:
    return PostDetail(
        **_post_summary(post).model_dump(),
        body=post.body,
        solution_comment_id=post.solution_comment_id,
        updated_at=post.updated_at,
        comments=[CommentOut(id=c.id, body=c.body, author=_author(c.author), created_at=c.created_at) for c in post.comments],
        can_write=domain_access(db, user, post.vendor_id) == "member",
        can_edit=post.author_id == user.id or is_admin(user),
    )


def _to_utc(value: datetime) -> datetime:
    # SQLite 는 시간대를 버리고 저장하므로, 저장 전에 반드시 UTC 로 맞춘다.
    return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _clean_event(body: EventIn) -> dict:
    starts = _to_utc(body.starts_at)
    ends = _to_utc(body.ends_at) if body.ends_at else None
    if ends and ends < starts:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "종료 시각이 시작 시각보다 빠릅니다.")
    return {
        "title": body.title.strip(),
        "description": body.description.strip(),
        "starts_at": starts,
        "ends_at": ends,
        "join_url": (body.join_url or "").strip() or None,
    }


def _editable_event(db: Session, user: User, event_id: int) -> SessionEvent:
    event = db.get(SessionEvent, event_id)
    if event is None or domain_access(db, user, event.vendor_id) == "none":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "일정을 찾을 수 없습니다.")
    if event.organizer_id != user.id and not is_admin(user):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "등록한 사람만 수정할 수 있습니다.")
    return event


def _event_out(user: User, event: SessionEvent, access: str) -> EventOut:
    names = [a.user.name for a in event.attendees]
    return EventOut(
        id=event.id,
        vendor_id=event.vendor_id,
        title=event.title,
        description=event.description,
        starts_at=event.starts_at,
        ends_at=event.ends_at,
        join_url=event.join_url,
        organizer=_author(event.organizer),
        attendee_count=len(names),
        attendees=names,
        attending=any(a.user_id == user.id for a in event.attendees),
        can_edit=access == "member" and (event.organizer_id == user.id or is_admin(user)),
    )


def _grant_active(g: AccessGrant) -> bool:
    if g.status != GrantStatus.APPROVED:
        return False
    if g.grant_type == "member":
        return bool(g.user.partner) and g.vendor in g.user.partner.vendors
    return bool(g.expires_at) and as_utc(g.expires_at) > utcnow()


def _grant_or_404(db: Session, grant_id: int) -> AccessGrant:
    grant = db.get(AccessGrant, grant_id)
    if grant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "신청을 찾을 수 없습니다.")
    return grant


def _grant_out(db: Session, g: AccessGrant) -> AccessGrantOut:
    decider = db.get(User, g.decided_by) if g.decided_by else None
    return AccessGrantOut(
        id=g.id,
        user=_author(g.user),
        user_email=g.user.email,
        vendor_id=g.vendor_id,
        vendor_name=g.vendor.name,
        reason=g.reason,
        requested_days=g.requested_days,
        request_date=g.request_date,
        requester_name=g.requester_name,
        requester_email=g.requester_email,
        requester_company=g.requester_company,
        status=g.status,
        grant_type=g.grant_type,
        active=_grant_active(g),
        decided_by_name=decider.name if decider else None,
        decided_at=g.decided_at,
        expires_at=g.expires_at,
        decision_note=g.decision_note,
        created_at=g.created_at,
    )
