"""영업: 견적서 생성에 쓸 참고 자료 관리 (견적서 양식·로고는 파트너사 자산 API 를 함께 쓴다).

영업 사용자(track=sales)와 플랫폼 관리자만 쓸 수 있다. 자료는 회사(파트너사) 단위로 공유된다.
"""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_active_user, is_admin
from ..models import QuoteFile, Track, User, Vendor
from ..schemas import QuoteFileOut
from ..services.storage import get_storage
from .uploads import store_upload

router = APIRouter(prefix="/api/quote-files", tags=["견적서"])

Category = Literal["spec", "feature", "price", "other"]
ALLOWED = {".pdf", ".docx", ".xlsx", ".pptx", ".csv", ".txt", ".png", ".jpg", ".jpeg"}


def require_sales(user: User = Depends(get_active_user)) -> User:
    if not (is_admin(user) or user.track == Track.SALES):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "영업 계정만 쓸 수 있습니다.")
    return user


def _out(f: QuoteFile) -> QuoteFileOut:
    return QuoteFileOut(**QuoteFileOut.model_validate(f).model_dump(exclude={"vendor_name"}), vendor_name=f.vendor.name if f.vendor else None)


def _file_for(db: Session, user: User, file_id: int) -> QuoteFile:
    f = db.get(QuoteFile, file_id)
    if f is None or not (is_admin(user) or f.partner_id == user.partner_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "자료를 찾을 수 없습니다.")
    return f


@router.get("", response_model=list[QuoteFileOut])
def list_files(partner_id: int | None = None, user: User = Depends(require_sales), db: Session = Depends(get_db)) -> list[QuoteFileOut]:
    pid = partner_id if is_admin(user) and partner_id is not None else user.partner_id
    query = select(QuoteFile).where(QuoteFile.partner_id == pid).order_by(QuoteFile.created_at.desc())
    return [_out(f) for f in db.scalars(query)]


@router.post("", response_model=QuoteFileOut, status_code=status.HTTP_201_CREATED)
def upload_file(
    category: Category = Form("other"),
    vendor_id: int | None = Form(None),
    note: str | None = Form(None),
    partner_id: int | None = Form(None),
    file: UploadFile | None = File(None),
    storage_key: str | None = Form(None),
    filename: str | None = Form(None),
    user: User = Depends(require_sales),
    db: Session = Depends(get_db),
) -> QuoteFileOut:
    pid = partner_id if is_admin(user) and partner_id is not None else user.partner_id
    if pid is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "소속 회사를 지정하세요.")
    if file is None and not storage_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "파일을 선택하세요.")
    name = (file.filename if file is not None else filename) or storage_key or ""
    if Path(name).suffix.lower() not in ALLOWED:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"허용 형식: {', '.join(sorted(ALLOWED))}")
    if vendor_id is not None and db.get(Vendor, vendor_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "벤더를 찾을 수 없습니다.")
    ref, original = store_upload(f"quote-files/{pid}", file, storage_key, filename)
    f = QuoteFile(
        partner_id=pid,
        vendor_id=vendor_id,
        uploaded_by=user.id,
        category=category,
        filename=Path(original).name[:300],
        file_path=ref,
        note=(note or "").strip() or None,
    )
    db.add(f)
    db.commit()
    return _out(f)


@router.get("/{file_id}/download")
def download_file(file_id: int, user: User = Depends(require_sales), db: Session = Depends(get_db)) -> Response:
    f = _file_for(db, user, file_id)
    return get_storage().response(f.file_path, f.filename, "application/octet-stream")


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(file_id: int, user: User = Depends(require_sales), db: Session = Depends(get_db)) -> None:
    f = _file_for(db, user, file_id)
    db.delete(f)  # 저장소의 파일은 남겨 둔다 (기록 보존)
    db.commit()
