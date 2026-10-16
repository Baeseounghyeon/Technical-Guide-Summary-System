"""PC 폴더(backend/storage)에 있는 업로드·생성 파일을 Supabase Storage 로 옮기고 DB 의 경로를 바꾼다.

사용법 (backend 폴더, .env 에 STORAGE_BACKEND=supabase·SUPABASE_URL·SUPABASE_SERVICE_KEY 설정 후):
    .\\.venv\\Scripts\\python -m app.migrate_files_to_storage

이미 옮긴 것(경로가 절대 경로가 아닌 것)은 건너뛰므로 여러 번 실행해도 된다. PC 의 원본 파일은 지우지 않는다.
"""

import sys
from pathlib import Path

from sqlalchemy import select, update

from .config import settings
from .db import SessionLocal
from .models import CorrectionExport, Export, Partner, PartnerGuide, SourceDocument
from .services.storage import SupabaseStorage, get_storage

COLUMNS = [
    SourceDocument.file_path,
    PartnerGuide.file_path,
    Export.file_path,
    CorrectionExport.file_path,
    Partner.logo_path,
    Partner.docx_template_path,
    Partner.pptx_template_path,
]


def _key_for(path: Path) -> str:
    try:
        return path.resolve().relative_to(settings.storage_dir.resolve()).as_posix()
    except ValueError:
        return f"legacy/{path.name}"


def main() -> None:
    storage = get_storage()
    if not isinstance(storage, SupabaseStorage):
        sys.exit(".env 에 STORAGE_BACKEND=supabase 와 SUPABASE_URL, SUPABASE_SERVICE_KEY 를 먼저 넣으세요.")
    moved = missing = 0
    with SessionLocal() as db:
        for column in COLUMNS:
            table = column.class_
            for row_id, ref in db.execute(select(table.id, column).where(column.is_not(None))):
                path = Path(ref)
                if not path.is_absolute():
                    continue  # 이미 저장소 키
                if not path.is_file():
                    print(f"  파일 없음 (건너뜀): {table.__tablename__}#{row_id} {ref}")
                    missing += 1
                    continue
                key = storage.save(_key_for(path), path.read_bytes())
                db.execute(update(table).where(table.id == row_id).values({column.key: key}))
                db.commit()
                moved += 1
                print(f"  {table.__tablename__}#{row_id} → {key}")
    print(f"완료: {moved}개 옮김, {missing}개 파일 없음")


if __name__ == "__main__":
    main()
