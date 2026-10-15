from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", extra="ignore")

    database_url: str = f"sqlite:///{(BASE_DIR / 'data' / 'app.db').as_posix()}"
    storage_dir: Path = BASE_DIR / "storage"

    jwt_secret: str = "dev-only-secret-change-me-0123456789abcdef"
    jwt_expire_minutes: int = 60 * 12
    cors_origins: list[str] = ["http://localhost:5173"]

    admin_email: str | None = None
    admin_password: str | None = None

    llm_provider: str = "mock"  # mock | claude
    anthropic_api_key: str | None = None
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "medium"
    llm_concurrency: int = 4

    # 생성 문서(표지·이력 표)에 찍히는 날짜의 시간대
    display_timezone: str = "Asia/Seoul"

    worker_poll_seconds: float = 2.0
    # true 면 API 서버 프로세스 안에서 Worker 도 실행한다 (개발용). 운영에서는 별도 프로세스로 실행.
    embedded_worker: bool = False


settings = Settings()
