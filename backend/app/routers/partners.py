"""파트너사 로고·템플릿 관리 (플랫폼 관리자 또는 해당 파트너사 관리자)."""

import shutil
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import get_active_user, is_admin
from ..models import Partner, Role, User
from ..schemas import PartnerOut

router = APIRouter(prefix="/api/partners", tags=["파트너사"])

AssetKind = Literal["logo", "docx_template", "pptx_template"]
ALLOWED = {
    "logo": {".png", ".jpg", ".jpeg"},
    "docx_template": {".docx", ".dotx"},
    "pptx_template": {".pptx", ".potx"},
}


@router.get("/{partner_id}", response_model=PartnerOut)
def get_partner(partner_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> Partner:
    return _partner_for(db, user, partner_id, manage=False)


@router.post("/{partner_id}/assets/{kind}", response_model=PartnerOut)
def upload_asset(
    partner_id: int, kind: AssetKind, file: UploadFile = File(...),
    user: User = Depends(get_active_user), db: Session = Depends(get_db),
) -> Partner:
    partner = _partner_for(db, user, partner_id, manage=True)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED[kind]:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"허용 형식: {', '.join(sorted(ALLOWED[kind]))}")
    out_dir = settings.storage_dir / "partners" / str(partner.id)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{kind}_{uuid.uuid4().hex}{ext}"
    with out_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    setattr(partner, f"{kind}_path", str(out_path))
    db.commit()
    return partner


def _partner_for(db: Session, user: User, partner_id: int, *, manage: bool) -> Partner:
    partner = db.get(Partner, partner_id)
    if partner is None or not (is_admin(user) or user.partner_id == partner_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파트너사를 찾을 수 없습니다.")
    if manage and not (is_admin(user) or user.role == Role.PARTNER_ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "파트너사 관리자만 변경할 수 있습니다.")
    return partner
