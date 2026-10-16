"""SQLite 개발 DB 의 데이터를 .env 의 DATABASE_URL(PostgreSQL/Supabase) 로 옮긴다.

사용법 (backend 폴더에서):
    .\\.venv\\Scripts\\python -m app.migrate_to_postgres            # 기본: data/app.db
    .\\.venv\\Scripts\\python -m app.migrate_to_postgres 경로\\app.db

대상 DB 에 이미 데이터가 있으면 덮어쓰지 않고 멈춘다. 업로드 파일(storage 폴더)은 옮기지 않는다.
"""

import sys
from collections import defaultdict
from pathlib import Path

from sqlalchemy import create_engine, func, select, text, update

from .config import BASE_DIR
from .db import Base, engine as target, init_db


def migrate(sqlite_path: Path) -> None:
    if target.dialect.name != "postgresql":
        sys.exit(f".env 의 DATABASE_URL 이 PostgreSQL 이 아닙니다 (현재: {target.dialect.name}).")
    if not sqlite_path.exists():
        sys.exit(f"SQLite 파일이 없습니다: {sqlite_path}")

    source = create_engine(f"sqlite:///{sqlite_path.as_posix()}")
    print(f"원본: {sqlite_path}")
    print(f"대상: {target.url.render_as_string(hide_password=True)}")

    init_db()  # 대상에 테이블 생성 (+ RLS)
    tables = Base.metadata.sorted_tables
    with target.connect() as conn:
        filled = [t.name for t in tables if conn.scalar(select(func.count()).select_from(t))]
    if filled:
        sys.exit(f"대상 DB 에 이미 데이터가 있어 멈춥니다: {', '.join(filled)}")

    done: set[str] = set()
    pending_fk: list[tuple] = []  # (테이블, pk 값들, 컬럼, 값) — 아직 안 옮긴 행을 가리키는 외래 키는 나중에 채운다
    with source.connect() as src, target.begin() as dst:
        for table in tables:
            src_cols = {c["name"] for c in source.dialect.get_columns(src, table.name)} if source.dialect.has_table(src, table.name) else set()
            if not src_cols:
                print(f"  {table.name}: 원본에 없음, 건너뜀")
                done.add(table.name)
                continue
            cols = [c for c in table.columns if c.name in src_cols]
            # 자기 자신이나 아직 옮기지 않은 테이블을 가리키는 외래 키 컬럼
            later = {
                c.name for c in cols for fk in c.foreign_keys
                if fk.column.table.name == table.name or fk.column.table.name not in done
            }
            pk = [c.name for c in table.primary_key.columns]
            order = [table.c[name] for name in pk]
            rows = [dict(r._mapping) for r in src.execute(select(*cols).order_by(*order))]
            for row in rows:
                for name in later:
                    if row.get(name) is not None:
                        pending_fk.append((table, tuple(row[k] for k in pk), name, row[name]))
                        row[name] = None
            if rows:
                dst.execute(table.insert(), rows)
            done.add(table.name)
            print(f"  {table.name}: {len(rows)}건")

        by_table = defaultdict(int)
        for table, pk_values, name, value in pending_fk:
            cond = [table.c[k] == v for k, v in zip([c.name for c in table.primary_key.columns], pk_values)]
            dst.execute(update(table).where(*cond).values({name: value}))
            by_table[table.name] += 1
        for name, n in by_table.items():
            print(f"  {name}: 외래 키 {n}건 연결")

        # 직접 넣은 id 뒤로 자동 증가 번호를 맞춘다
        for table in tables:
            id_col = table.c.get("id")
            if id_col is None or not id_col.autoincrement:
                continue
            dst.execute(text(
                f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM \"{table.name}\"), 0) + 1, false)"
            ))
    print("완료")


if __name__ == "__main__":
    migrate(Path(sys.argv[1]) if len(sys.argv) > 1 else BASE_DIR / "data" / "app.db")
