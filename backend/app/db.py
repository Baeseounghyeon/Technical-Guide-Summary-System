from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings

_is_sqlite = settings.database_url.startswith("sqlite")

_is_postgres = settings.database_url.startswith("postgresql")

engine = create_engine(
    settings.database_url,
    # Supabase Transaction pooler(6543) 는 서버 측 prepared statement 를 지원하지 않으므로 끈다
    connect_args={"check_same_thread": False, "timeout": 30} if _is_sqlite
    else {"prepare_threshold": None} if _is_postgres else {},
    # Supabase 같은 원격 DB 는 유휴 연결이 끊길 수 있으므로 쓰기 전에 확인
    pool_pre_ping=not _is_sqlite,
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):
        # API 서버와 Worker가 같은 파일을 동시에 쓰므로 WAL 모드 사용
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    with SessionLocal() as db:
        yield db


def init_db() -> None:
    from . import models  # noqa: F401  (테이블 등록)

    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    if _is_sqlite and engine.url.database:
        Path(engine.url.database).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(engine)
    _add_missing_columns()
    if _is_postgres:
        _enable_row_level_security()


def _add_missing_columns() -> None:
    """기존 DB 에 새로 생긴 nullable 컬럼을 추가한다 (Alembic 도입 전 임시 방편).

    create_all 은 기존 테이블에 컬럼을 추가하지 않으므로, 모델에만 있고 DB 에 없는 컬럼을 ALTER TABLE 로 붙인다.
    """
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing and column.nullable:
                    ddl = column.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {ddl}'))


def _enable_row_level_security() -> None:
    """PostgreSQL(Supabase) 의 모든 테이블에 RLS 를 켠다.

    Supabase 는 public 스키마 테이블을 공개 Data API(anon 키)로 노출하므로, 정책 없이 RLS 만 켜서 그 경로를 막는다.
    이 서버는 테이블 소유자 계정으로 직접 접속하므로 RLS 의 영향을 받지 않는다.
    """
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            conn.execute(text(f'ALTER TABLE "{table.name}" ENABLE ROW LEVEL SECURITY'))
