"""DB 테이블 기반 작업 큐. 처리량이 커지면 Celery/arq 로 교체한다."""

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..models import Job, JobKind, JobStatus, utcnow


def enqueue(db: Session, kind: JobKind, payload: dict) -> Job:
    """작업을 등록한다. 커밋은 호출하는 쪽에서 한다."""
    job = Job(kind=kind, payload=payload)
    db.add(job)
    return job


def claim_next(db: Session) -> Job | None:
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


def requeue_stale(db: Session) -> int:
    """Worker가 비정상 종료되어 RUNNING 으로 남은 작업을 다시 대기열에 넣는다 (Worker 1개 기준)."""
    result = db.execute(update(Job).where(Job.status == JobStatus.RUNNING).values(status=JobStatus.QUEUED))
    db.commit()
    return result.rowcount
