"""파일 업로드 공통 처리.

서버리스 배포에서는 요청 크기 제한(4.5MB) 때문에 브라우저가 Supabase Storage 로 바로 올린다:
  1) POST /api/uploads {filename} → {key, upload_url}
  2) 브라우저가 upload_url 로 PUT
  3) 원래 업로드 API 에 file 대신 storage_key + filename 을 보낸다.
로컬 저장소에서는 지금처럼 multipart file 로 받는다.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel

from ..deps import get_active_user
from ..models import User
from ..services.storage import get_storage

router = APIRouter(prefix="/api", tags=["업로드"])

INCOMING = "incoming/"
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".dotx", ".potx", ".png", ".jpg", ".jpeg"}


class UploadSlotIn(BaseModel):
    filename: str


class UploadSlotOut(BaseModel):
    key: str
    upload_url: str


@router.get("/uploads/config")
def upload_config() -> dict:
    return {"direct_upload": get_storage().direct_upload}


@router.post("/uploads", response_model=UploadSlotOut)
def create_upload_slot(body: UploadSlotIn, user: User = Depends(get_active_user)) -> UploadSlotOut:
    ext = Path(body.filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "지원하지 않는 파일 형식입니다.")
    key = f"{INCOMING}{uuid.uuid4().hex}{ext}"
    return UploadSlotOut(key=key, upload_url=get_storage().sign_upload(key))


def store_upload(
    folder: str, file: UploadFile | None, storage_key: str | None, filename: str | None
) -> tuple[str, str] | None:
    """업로드된 파일을 저장소에 두고 (DB 에 넣을 참조, 원래 파일명)을 돌려준다. 파일이 없으면 None."""
    if file is not None:
        name = file.filename or ""
        ref = get_storage().save(f"{folder}/{uuid.uuid4().hex}{Path(name).suffix.lower()}", file.file)
        return ref, name
    if storage_key:
        # 이 서버가 발급한 업로드 자리만 받는다 (다른 파일 경로를 가리키지 못하게).
        if not storage_key.startswith(INCOMING) or "/" in storage_key[len(INCOMING):] or not get_storage().exists(storage_key):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "업로드한 파일을 찾을 수 없습니다. 다시 올려 주세요.")
        return storage_key, filename or storage_key
    return None
