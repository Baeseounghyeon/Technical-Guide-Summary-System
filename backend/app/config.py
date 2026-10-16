from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'app.db').as_posix()}"
    storage_dir: Path = BASE_DIR / "storage"
    # 파일 저장소: local(storage_dir 폴더) | supabase(Supabase Storage, 서버리스 배포용)
    storage_backend: str = "local"
    supabase_url: str | None = None  # 예: https://프로젝트ID.supabase.co
    supabase_service_key: str | None = None  # service_role 또는 sb_secret_ 키 (서버 전용, 절대 공개 금지)
    supabase_bucket: str = "techguide"

    jwt_secret: str = "dev-only-secret-change-me-0123456789abcdef"
    jwt_expire_minutes: int = 60 * 12
    cors_origins: list[str] = ["http://localhost:5173"]

    admin_email: str | None = None
    admin_password: str | None = None

    llm_provider: str = "mock"  # mock | claude_code (본인 구독) | claude (API 키)
    llm_concurrency: int = 4

    # LLM_PROVIDER=claude: Claude API
    anthropic_api_key: str | None = None
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "medium"

    # LLM_PROVIDER=claude_code: Claude Code CLI + 본인 구독 (개인 사용 전용)
    claude_code_path: str = "claude"  # PATH 에서 못 찾으면 %USERPROFILE%\.local\bin\claude.exe 를 확인
    claude_code_model: str = "opus"  # opus | sonnet ... 구독 사용량을 아끼려면 sonnet
    claude_code_timeout_seconds: int = 900

    # 생성 문서(표지·이력 표)에 찍히는 날짜의 시간대
    display_timezone: str = "Asia/Seoul"

    worker_poll_seconds: float = 2.0
    # true 면 API 서버 프로세스 안에서 Worker 도 실행한다 (개발용). 운영에서는 별도 프로세스로 실행.
    embedded_worker: bool = False

    # 서버리스(Vercel) 작업 처리: 요청 한 번에 쓸 수 있는 시간(초). 지정하면 긴 작업을 이 시간 단위로 나눠 처리하고,
    # 작업을 등록한 응답에 X-Jobs-Queued 헤더를 붙여 화면이 /api/jobs/kick 으로 처리를 깨우게 한다.
    job_time_budget_seconds: float | None = None
    # /api/jobs/run 호출용 비밀값 (Supabase pg_cron 이 1분마다 호출). 없으면 그 경로는 막힌다.
    cron_secret: str | None = None


settings = Settings()
