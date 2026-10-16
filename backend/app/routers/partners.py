"""파트너사 로고·템플릿 관리 (플랫폼 관리자 또는 해당 파트너사 관리자)."""

from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_active_user, is_admin
from ..models import Partner, Role, User
from ..schemas import PartnerOut
from ..services.storage import get_storage
from .uploads import store_upload

router = APIRouter(prefix="/api/partners", tags=["파트너사"])

AssetKind = Literal["logo", "docx_template", "pptx_template"]
ALLOWED = {
    "logo": {".png", ".jpg", ".jpeg"},
    "docx_template": {".docx", ".dotx"},
    "pptx_template": {".pptx", ".potx"},
}
LOGO_MEDIA_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


@router.get("/{partner_id}", response_model=PartnerOut)
def get_partner(partner_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> Partner:
    return _partner_for(db, user, partner_id, manage=False)


@router.get("/{partner_id}/logo")
def get_logo(partner_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> Response:
    """설정 화면 미리보기용. 해당 파트너사 소속이면 누구나 볼 수 있다."""
    partner = _partner_for(db, user, partner_id, manage=False)
    path = Path(partner.logo_path) if partner.logo_path else None
    if path is None or not get_storage().exists(partner.logo_path):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "등록된 로고가 없습니다.")
    return get_storage().inline_response(partner.logo_path, LOGO_MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream"))


@router.post("/{partner_id}/assets/{kind}", response_model=PartnerOut)
def upload_asset(
    partner_id: int, kind: AssetKind, file: UploadFile | None = File(None),
    storage_key: str | None = Form(None), filename: str | None = Form(None),
    user: User = Depends(get_active_user), db: Session = Depends(get_db),
) -> Partner:
    partner = _partner_for(db, user, partner_id, manage=True)
    if file is None and not storage_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "파일을 선택하세요.")
    ext = Path(file.filename or "" if file is not None else storage_key).suffix.lower()
    if ext not in ALLOWED[kind]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"허용 형식: {', '.join(sorted(ALLOWED[kind]))}")
    ref, _ = store_upload(f"partners/{partner.id}", file, storage_key, filename)
    setattr(partner, f"{kind}_path", ref)
    db.commit()
    return partner


def _partner_for(db: Session, user: User, partner_id: int, *, manage: bool) -> Partner:
    partner = db.get(Partner, partner_id)
    if partner is None or not (is_admin(user) or user.partner_id == partner_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파트너사를 찾을 수 없습니다.")
    if manage and not (is_admin(user) or user.role == Role.PARTNER_ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "파트너사 관리자만 변경할 수 있습니다.")
    return partner
