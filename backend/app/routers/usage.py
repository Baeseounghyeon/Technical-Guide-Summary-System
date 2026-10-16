"""AI 사용량: 내 회사의 이번 달 사용 현황 (요약 시작 전 예상 사용량 표시용)."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_active_user, get_document_for_user
from ..models import User
from ..services.usage import pages_for_chars, summary_for

router = APIRouter(prefix="/api", tags=["사용량"])


@router.get("/usage")
def my_usage(document_id: int | None = None, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> dict:
    out = summary_for(db, user)
    if document_id is not None:
        doc = get_document_for_user(db, user, document_id)
        chars = sum(len(s.text) for s in doc.sections if s.included and s.text.strip())
        out["estimate_pages"] = pages_for_chars(chars) if chars else 0
    return out
