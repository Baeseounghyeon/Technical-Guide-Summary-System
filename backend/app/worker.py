"""백그라운드 작업 처리기. 실행: python -m app.worker"""

import logging
import time

from .config import settings
from .db import SessionLocal, init_db
from .models import Job, JobStatus, utcnow
from .services.jobs import JobPaused, claim_next, has_time_for_llm_call, requeue_stale, set_deadline
from .services import partner_review, pipeline

HANDLERS = {**pipeline.HANDLERS, **partner_review.HANDLERS}

log = logging.getLogger("worker")


def run_job(job_id: int) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        handle, on_failure = HANDLERS[job.kind]
        log.info("작업 시작 #%s %s %s", job.id, job.kind, job.payload)
        try:
            handle(db, job)
            job.status = JobStatus.DONE
        except JobPaused:
            # 시간 제한(서버리스)으로 멈춤: 진행분은 저장됐으니 대기열로 되돌려 다음 처리 때 이어서 한다.
            log.info("작업 일시 중지 #%s (다음 처리 때 이어서)", job_id)
            job.status = JobStatus.QUEUED
            db.commit()
            return
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


def run_pending_jobs(time_budget: float | None = None) -> int:
    """대기 중인 작업을 처리하고 처리한 개수를 돌려준다.

    time_budget(초)을 주면 그 시간 안에서만 처리한다(서버리스). 긴 작업은 중간에 멈추고 대기열로 돌아간다.
    """
    set_deadline(time_budget)
    count = 0
    while has_time_for_llm_call():
        with SessionLocal() as db:
            job = claim_next(db)
        if job is None:
            return count
        run_job(job.id)
        count += 1
    return count


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
