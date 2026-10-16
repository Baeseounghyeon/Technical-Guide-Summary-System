"""AI 사용량 한도와 비용 기록.

- 회사(파트너사)별 월 처리량 한도(쪽 환산): 요약·재생성·비교를 요청할 때 미리 차감한다.
- 사용자별 하루 재생성 횟수 한도.
- 전체 월 예산(달러): 실제 토큰 사용량으로 계산한 비용이 넘으면 모든 AI 요청을 막는다.
플랫폼 관리자는 회사 한도·재생성 한도에서 제외되지만 전체 예산은 똑같이 적용된다.
"""

import math
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Partner, Role, UsageRecord, User
from .llm.base import LLMUsage

# 100만 토큰당 달러 (입력, 출력, 캐시 읽기). 캐시 쓰기는 입력의 1.25배.
PRICES = {
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-opus-5": (5.0, 25.0, 0.50),
    "claude-opus-4-8": (5.0, 25.0, 0.50),
    "claude-sonnet-5": (2.0, 10.0, 0.20),
}
_FALLBACK_PRICE = PRICES["claude-opus-5-5"]


def pages_for_chars(chars: int) -> int:
    return max(1, math.ceil(chars / settings.chars_per_page))


def cost_of(usages: list[LLMUsage]) -> float:
    total = 0.0
    for u in usages:
        p_in, p_out, p_cache = PRICES.get(u.model, _FALLBACK_PRICE)
        total += (
            u.input_tokens * p_in
            + u.output_tokens * p_out
            + u.cache_read_tokens * p_cache
            + u.cache_write_tokens * p_in * 1.25
        ) / 1_000_000
    return total


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def month_cost(db: Session) -> float:
    return float(db.scalar(select(func.coalesce(func.sum(UsageRecord.cost_usd), 0)).where(UsageRecord.created_at >= month_start())))


def budget_exceeded(db: Session) -> bool:
    return bool(settings.monthly_budget_usd) and month_cost(db) >= settings.monthly_budget_usd


def partner_quota(partner: Partner | None) -> int:
    if partner is not None and partner.monthly_page_quota is not None:
        return partner.monthly_page_quota
    return settings.default_monthly_page_quota


def partner_used_pages(db: Session, partner_id: int | None) -> int:
    if partner_id is None:
        return 0
    return int(
        db.scalar(
            select(func.coalesce(func.sum(UsageRecord.pages), 0)).where(
                UsageRecord.partner_id == partner_id, UsageRecord.created_at >= month_start()
            )
        )
    )


def regenerations_today(db: Session, user_id: int) -> int:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    return int(
        db.scalar(
            select(func.count()).where(
                UsageRecord.user_id == user_id, UsageRecord.kind == "regenerate", UsageRecord.created_at >= since
            )
        )
    )


def summary_for(db: Session, user: User) -> dict:
    """화면에 보여 줄 내 회사의 이번 달 사용 현황."""
    unlimited = user.role == Role.PLATFORM_ADMIN
    partner = db.get(Partner, user.partner_id) if user.partner_id else None
    quota = partner_quota(partner)
    used = partner_used_pages(db, user.partner_id)
    return {
        "unlimited": unlimited,
        "quota_pages": quota,
        "used_pages": used,
        "remaining_pages": max(0, quota - used),
        "regenerations_today": regenerations_today(db, user.id),
        "regeneration_limit": settings.daily_regenerate_limit,
        "budget_exceeded": budget_exceeded(db),
    }


def charge(
    db: Session,
    user: User,
    kind: str,
    pages: int,
    *,
    guide_id: int | None = None,
    partner_guide_id: int | None = None,
) -> UsageRecord:
    """한도를 확인하고 사용 기록을 남긴다 (커밋은 호출하는 쪽에서). 넘으면 HTTP 오류로 거절한다."""
    if budget_exceeded(db):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "이번 달 AI 사용 예산을 모두 사용했습니다. 다음 달에 다시 시도하거나 관리자에게 문의하세요.",
        )
    if user.role != Role.PLATFORM_ADMIN:
        if kind == "regenerate" and regenerations_today(db, user.id) >= settings.daily_regenerate_limit:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"재생성은 하루 {settings.daily_regenerate_limit}회까지 할 수 있습니다. 내일 다시 시도하거나 직접 수정하세요.",
            )
        partner = db.get(Partner, user.partner_id) if user.partner_id else None
        quota = partner_quota(partner)
        used = partner_used_pages(db, user.partner_id)
        if used + pages > quota:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"이번 달 회사 AI 처리 한도를 넘습니다 (필요 {pages}쪽, 남은 양 {max(0, quota - used)}쪽 / 월 {quota}쪽). "
                "요약할 목차를 줄이거나 관리자에게 한도 조정을 요청하세요.",
            )
    record = UsageRecord(
        partner_id=user.partner_id,
        user_id=user.id,
        kind=kind,
        pages=pages,
        guide_id=guide_id,
        partner_guide_id=partner_guide_id,
    )
    db.add(record)
    db.flush()
    return record


def add_tokens(db: Session, record_id: int | None, usages: list[LLMUsage], *, kind: str = "job") -> None:
    """작업 처리 후 실제 토큰 사용량과 비용을 기록에 더한다 (기록이 없으면 새로 만든다)."""
    if not usages:
        return
    record = db.get(UsageRecord, record_id) if record_id else None
    if record is None:
        record = UsageRecord(kind=kind, pages=0)
        db.add(record)
    record.input_tokens = (record.input_tokens or 0) + sum(u.input_tokens + u.cache_read_tokens + u.cache_write_tokens for u in usages)
    record.output_tokens = (record.output_tokens or 0) + sum(u.output_tokens for u in usages)
    record.cost_usd = (record.cost_usd or 0.0) + cost_of(usages)
