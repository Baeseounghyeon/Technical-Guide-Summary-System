"""서버리스(Vercel)용 작업 처리 진입점.

상주 Worker 가 없으므로 요청이 들어올 때 정해진 시간(JOB_TIME_BUDGET_SECONDS) 동안 대기 작업을 처리한다.
- POST /api/jobs/kick: 작업을 등록한 화면이 바로 호출한다 (응답을 기다리지 않음).
- GET|POST /api/jobs/run: Supabase pg_cron 이 1분마다 호출한다 (CRON_SECRET 필요).
처리하고도 작업이 남으면 /api/jobs/run 을 다시 불러 다음 함수 실행으로 이어 간다.
"""

import hmac
import logging

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from ..config import settings
from ..db import SessionLocal
from ..deps import get_active_user
from ..models import User
from ..services.jobs import has_queued

router = APIRouter(prefix="/api/jobs", tags=["작업 처리"])
log = logging.getLogger("jobs")


def _process(request: Request) -> dict:
    if not settings.job_time_budget_seconds:
        return {"processed": 0, "note": "상주 Worker 가 처리합니다."}
    from ..worker import run_pending_jobs

    processed = run_pending_jobs(settings.job_time_budget_seconds)
    with SessionLocal() as db:
        remaining = has_queued(db)
    if remaining and settings.cron_secret:
        _chain(str(request.base_url))
    return {"processed": processed, "remaining": remaining}


def _chain(base_url: str) -> None:
    """남은 작업을 새 함수 실행에서 이어서 처리하도록 자기 자신을 호출한다 (응답은 기다리지 않음)."""
    try:
        httpx.post(
            base_url.rstrip("/") + "/api/jobs/run",
            headers={"Authorization": f"Bearer {settings.cron_secret}"},
            timeout=3,
        )
    except httpx.TimeoutException:
        pass  # 상대 함수는 계속 실행된다
    except httpx.HTTPError:
        log.exception("다음 작업 처리 호출 실패 (pg_cron 이 이어서 처리)")


@router.post("/kick")
def kick(request: Request, _user: User = Depends(get_active_user)) -> dict:
    return _process(request)


@router.post("/run")
def run(request: Request, authorization: str | None = Header(None)) -> dict:
    return _run_with_secret(request, authorization)


@router.get("/run")
def run_get(request: Request, authorization: str | None = Header(None)) -> dict:
    return _run_with_secret(request, authorization)


def _run_with_secret(request: Request, authorization: str | None) -> dict:
    expected = f"Bearer {settings.cron_secret}" if settings.cron_secret else None
    if not expected or not hmac.compare_digest(authorization or "", expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "인증 실패")
    return _process(request)
