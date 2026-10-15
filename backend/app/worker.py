"""백그라운드 작업 처리기. 실행: python -m app.worker"""

import logging
import time

from .config import settings
from .db import SessionLocal, init_db
from .models import Job, JobStatus, utcnow
from .services.jobs import claim_next, requeue_stale
from .services.pipeline import HANDLERS

log = logging.getLogger("worker")


def run_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        handle, on_failure = HANDLERS[job.kind]
        log.info("작업 시작 #%s %s %s", job.id, job.kind, job.payload)
        try:
            handle(db, job)
            job.status = JobStatus.DONE
        except Exception as e:
            log.exception("작업 실패 #%s", job_id)
            db.rollback()
            job = db.get(Job, job_id)
            error = f"{type(e).__name__}: {e}"[:2000]
            on_failure(db, job, error)
            job.status = JobStatus.FAILED
            job.error = error
        job.finished_at = utcnow()
        db.commit()


def run_pending_jobs() -> int:
    """대기 중인 작업을 모두 처리하고 처리한 개수를 돌려준다."""
    count = 0
    while True:
        with SessionLocal() as db:
            job = claim_next(db)
        if job is None:
            return count
        run_job(job.id)
        count += 1


def worker_loop() -> None:
    with SessionLocal() as db:
        if n := requeue_stale(db):
            log.info("중단된 작업 %d건을 다시 대기열에 넣었습니다.", n)
    log.info("Worker 시작 (요약 엔진: %s)", settings.llm_provider)
    while True:
        try:
            if run_pending_jobs() == 0:
                time.sleep(settings.worker_poll_seconds)
        except Exception:  # DB 연결 오류 등으로 루프 전체가 멈추지 않게 한다.
            log.exception("Worker 루프 오류")
            time.sleep(settings.worker_poll_seconds)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    worker_loop()


if __name__ == "__main__":
    main()
