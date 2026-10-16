"""DB 테이블 기반 작업 큐. 처리량이 커지면 Celery/arq 로 교체한다."""

import time
from contextvars import ContextVar
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Job, JobKind, JobStatus, utcnow

# 요청 처리 중 작업이 등록됐는지 표시 (서버리스에서 응답 헤더로 알려 화면이 처리를 깨우게 한다)
enqueued_in_request: ContextVar[list | None] = ContextVar("enqueued_in_request", default=None)

# 지금 처리 중인 작업 묶음의 마감 시각 (time.monotonic 기준, None 이면 제한 없음)
_deadline: ContextVar[float | None] = ContextVar("job_deadline", default=None)

# 마감이 이만큼(초) 안 남았으면 새 LLM 호출을 시작하지 않는다
LLM_CALL_RESERVE_SECONDS = 90


class JobPaused(Exception):
    """시간이 모자라 작업을 중간에 멈췄다. 진행 상황은 저장됐고 다음 처리 때 이어서 한다."""


def enqueue(db: Session, kind: JobKind, payload: dict) -> Job:
    """작업을 등록한다. 커밋은 호출하는 쪽에서 한다."""
    job = Job(kind=kind, payload=payload)
    db.add(job)
    if (flag := enqueued_in_request.get()) is not None:
        flag.append(kind)
    return job


def set_deadline(seconds: float | None) -> None:
    _deadline.set(time.monotonic() + seconds if seconds else None)


def time_left() -> float:
    deadline = _deadline.get()
    return float("inf") if deadline is None else deadline - time.monotonic()


def has_time_for_llm_call() -> bool:
    return time_left() > LLM_CALL_RESERVE_SECONDS


def claim_next(db: Session) -> Job | None:
    if settings.job_time_budget_seconds:
        _requeue_abandoned(db)
    job_id = db.scalar(select(Job.id).where(Job.status == JobStatus.QUEUED).order_by(Job.id).limit(1))
    if job_id is None:
        return None
    # 여러 Worker가 같은 작업을 가져가지 않도록 상태 조건을 걸고 갱신한다.
    result = db.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.QUEUED)
        .values(status=JobStatus.RUNNING, started_at=utcnow())
    )
    db.commit()
    if result.rowcount != 1:
        return None
    return db.get(Job, job_id)


def _requeue_abandoned(db: Session) -> None:
    """서버리스 함수가 시간 초과로 강제 종료돼 RUNNING 으로 남은 작업을 다시 대기열에 넣는다."""
    limit = utcnow() - timedelta(seconds=settings.job_time_budget_seconds * 2 + 60)
    db.execute(
        update(Job).where(Job.status == JobStatus.RUNNING, Job.started_at < limit).values(status=JobStatus.QUEUED)
    )
    db.commit()


def requeue_stale(db: Session) -> int:
    """Worker가 비정상 종료되어 RUNNING 으로 남은 작업을 다시 대기열에 넣는다 (Worker 1개 기준)."""
    result = db.execute(update(Job).where(Job.status == JobStatus.RUNNING).values(status=JobStatus.QUEUED))
    db.commit()
    return result.rowcount


def has_queued(db: Session) -> bool:
    return db.scalar(select(Job.id).where(Job.status == JobStatus.QUEUED).limit(1)) is not None
