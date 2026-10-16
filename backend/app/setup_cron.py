"""Supabase pg_cron 으로 1분마다 배포된 서버의 /api/jobs/run 을 호출하게 등록한다 (서버리스 작업 처리 보조).

사용법 (backend 폴더, .env 의 DATABASE_URL 이 Supabase 이고 CRON_SECRET 이 Vercel 과 같은 값일 때):
    .\\.venv\\Scripts\\python -m app.setup_cron https://내-프로젝트.vercel.app
    .\\.venv\\Scripts\\python -m app.setup_cron --remove      # 등록 해제
"""

import sys

from sqlalchemy import text

from .config import settings
from .db import engine

JOB_NAME = "techguide-run-jobs"


def main(argv: list[str]) -> None:
    if engine.dialect.name != "postgresql":
        sys.exit(".env 의 DATABASE_URL 이 Supabase(PostgreSQL) 가 아닙니다.")
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_cron"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_net"))
        exists = conn.scalar(text("SELECT count(*) FROM cron.job WHERE jobname = :n"), {"n": JOB_NAME})
        if exists:
            conn.execute(text("SELECT cron.unschedule(:n)"), {"n": JOB_NAME})
        if argv and argv[0] == "--remove":
            print("등록을 해제했습니다.")
            return
        if not argv or not argv[0].startswith("https://"):
            sys.exit("배포 주소를 https://... 형식으로 넣어 주세요.")
        if not settings.cron_secret:
            sys.exit(".env 에 CRON_SECRET 을 Vercel 과 같은 값으로 넣어 주세요.")
        url = argv[0].rstrip("/") + "/api/jobs/run"
        # pg_net 은 응답을 기다리지 않는다. 짧은 timeout 이어도 Vercel 함수는 끝까지 실행된다.
        command = (
            "SELECT net.http_post("
            f"url := '{url}', "
            f"headers := jsonb_build_object('Authorization', 'Bearer {settings.cron_secret}'), "
            "timeout_milliseconds := 5000)"
        )
        conn.execute(text("SELECT cron.schedule(:n, '* * * * *', :c)"), {"n": JOB_NAME, "c": command})
    print(f"등록 완료: 1분마다 {url} 호출")


if __name__ == "__main__":
    main(sys.argv[1:])
