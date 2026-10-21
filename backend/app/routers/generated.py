"""생성한 견적서(목록·받기·삭제)와 생성한 가이드(요약 가이드) 목록.
견적서 만들기는 routers/quote_builder.py. (규격서 생성 기능은 2026-10-21 삭제)"""

import re
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_active_user, is_admin
from ..models import GeneratedDocument, Guide, SourceDocument, User
from ..schemas import UTCDateTime
from ..services.exporters.quote_export import MEDIA

router = APIRouter(prefix="/api", tags=["생성한 견적서"])

FormType = Literal["quote"]
_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|]')
# 견적서에 쓴 문서 종류 (문서 등록의 제품 가격표·매입 금액) — 생성한 견적서 표의 '가격표·매입 금액' 칸
EXTRA_KINDS = {"price_list": "제품 가격표", "purchase": "매입 금액"}


class AttachmentOut(BaseModel):
    kind: str  # price_list | purchase
    label: str  # 제품 가격표 | 매입 금액
    document_id: int
    title: str | None


class GeneratedOut(BaseModel):
    id: int
    doc_type: str
    title: str
    fields: dict  # 견적서: 양식·항목 표·작성자·계산 설정
    formats: list[str] = ["pdf", "docx"]  # 받을 수 있는 형식
    version: int
    root_id: int
    based_on_id: int | None
    source_document_id: int | None
    source_document_title: str | None
    attachments: list[AttachmentOut] = []
    created_by: int
    created_by_name: str
    partner_name: str | None
    created_at: UTCDateTime


def _attachment_docs(db: Session, ids: dict | None) -> list[tuple[str, SourceDocument]]:
    """저장된 첨부 id → (종류, 문서). 지워진(휴지통) 문서는 뺀다."""
    out = []
    for kind in EXTRA_KINDS:
        value = (ids or {}).get(kind)
        for doc_id in value if isinstance(value, list) else [value]:  # 견적서는 매입 견적이 여러 건
            doc = db.get(SourceDocument, doc_id) if doc_id else None
            if doc is not None and doc.deleted_at is None:
                out.append((kind, doc))
    return out


def _out(db: Session, g: GeneratedDocument) -> GeneratedOut:
    return GeneratedOut(
        id=g.id,
        doc_type=g.doc_type,
        title=g.title,
        fields=g.fields or {},
        formats=_formats(g),
        version=g.version,
        root_id=g.root_id or g.id,
        based_on_id=g.based_on_id,
        source_document_id=g.source_document_id,
        source_document_title=g.source_document.title if g.source_document else None,
        attachments=[
            AttachmentOut(kind=k, label=EXTRA_KINDS[k], document_id=d.id, title=d.title)
            for k, d in _attachment_docs(db, g.attachments)
        ],
        created_by=g.created_by,
        created_by_name=g.creator.name,
        partner_name=g.partner.name if g.partner else None,
        created_at=g.created_at,
    )


def _formats(g: GeneratedDocument) -> list[str]:
    if g.doc_type == "quote":
        from ..services.exporters.quote_export import formats_for

        return formats_for((g.fields or {}).get("template_ext"))
    return ["pdf", "docx"]


def _get_generated(db: Session, user: User, generated_id: int) -> GeneratedDocument:
    """본인이 만든 것, 같은 조직이 만든 것, 관리자는 전부."""
    g = db.get(GeneratedDocument, generated_id)
    if g is None or not (is_admin(user) or g.created_by == user.id or (g.partner_id and g.partner_id == user.partner_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "생성한 문서를 찾을 수 없습니다.")
    return g


@router.get("/generated", response_model=list[GeneratedOut])
def list_generated(
    doc_type: FormType, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> list[GeneratedOut]:
    """생성한 ○○: 내가 만든 문서의 모든 버전 (관리자는 전체). 최신이 먼저."""
    query = select(GeneratedDocument).where(GeneratedDocument.doc_type == doc_type).order_by(GeneratedDocument.created_at.desc())
    if not is_admin(user):
        query = query.where(GeneratedDocument.created_by == user.id)
    return [_out(db, g) for g in db.scalars(query)]


@router.get("/generated/{generated_id}", response_model=GeneratedOut)
def get_generated(generated_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> GeneratedOut:
    return _out(db, _get_generated(db, user, generated_id))


@router.delete("/generated/{generated_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_generated(generated_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> None:
    """생성한 문서 삭제: 같은 이력(모든 버전)을 함께 지운다. 만든 사람이나 관리자만."""
    g = _get_generated(db, user, generated_id)
    root = g.root_id or g.id
    group = list(db.scalars(select(GeneratedDocument).where(or_(GeneratedDocument.id == root, GeneratedDocument.root_id == root))))
    if not is_admin(user) and any(x.created_by != user.id for x in group):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "직접 만든 문서만 삭제할 수 있습니다.")
    for x in sorted(group, key=lambda x: x.version, reverse=True):
        db.delete(x)
    db.commit()


@router.get("/generated/{generated_id}/download")
def download_generated(
    generated_id: int,
    format: Literal["pdf", "docx", "xlsx"] = Query("pdf"),
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> Response:
    g = _get_generated(db, user, generated_id)
    meta = [
        ("작성자", g.creator.name),
        ("소속", g.partner.name if g.partner else "-"),
        ("작성일", f"{g.created_at:%Y-%m-%d}"),
        ("버전", f"v{g.version}"),
    ]
    if format not in _formats(g):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"이 문서는 {', '.join(_formats(g))} 형식으로 받을 수 있습니다.")
    if g.doc_type != "quote":
        raise HTTPException(status.HTTP_410_GONE, "규격서 생성 기능은 삭제되어 받을 수 없습니다.")
    data = _quote_file(db, user, g, format, meta)
    name = f"{_UNSAFE_NAME.sub('_', g.title)[:100]}_v{g.version}.{format}"
    return Response(data, media_type=MEDIA[format], headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote(name)}"})


def _quote_file(db: Session, user: User, g: GeneratedDocument, fmt: str, meta: list) -> bytes:
    """견적서 파일: 양식과 같은 형식이면 양식을 채우고, 아니면 기본 양식. 양식이 지워졌으면 기본 양식."""
    from ..models import QuoteTemplate
    from .quote_builder import render

    fields = g.fields or {}
    template = db.get(QuoteTemplate, fields["template_id"]) if fields.get("template_id") else None
    return render(fields, template, fmt, version=f"v{g.version}")


# ---------- 생성한 가이드 (요약 가이드) ----------


@router.get("/my-guides")
def my_guides(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[dict]:
    """생성한 가이드: 내가 만든 요약 가이드와 최종 문서 생성 이력 (관리자는 전체)."""
    query = (
        select(Guide)
        .join(SourceDocument, SourceDocument.id == Guide.document_id)
        .where(SourceDocument.deleted_at.is_(None))
        .order_by(Guide.created_at.desc())
    )
    if not is_admin(user):
        query = query.where(Guide.created_by == user.id)
    rows = []
    for g in db.scalars(query):
        d = g.document
        rows.append(
            {
                "id": g.id,
                "document_id": d.id,
                "document_title": d.title or d.url or f"문서 {d.id}",
                "vendor_name": d.vendor.name,
                "product": d.product,
                "product_detail": d.product_detail,
                "target_language": g.target_language,
                "status": g.status,
                "created_at": g.created_at.isoformat(),
                "exports": [
                    {"id": e.id, "format": e.format, "doc_version": e.doc_version, "status": e.status, "created_at": e.created_at.isoformat()}
                    for e in g.exports
                ],
            }
        )
    return rows
