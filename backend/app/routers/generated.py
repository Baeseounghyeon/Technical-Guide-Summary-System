"""규격서·견적서 생성: 필수 입력 항목을 채워(재사용할 문서에서 가져와 고칠 수도 있음) PDF·Word 로 만든다.
생성 기록은 버전별로 남아 '생성한 ○○'에서 이력을 본다. 생성한 가이드(요약 가이드) 목록도 여기서 준다."""

import re
from urllib.parse import quote
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_active_user, get_readable_document, is_admin, require_permission
from ..form_fields import FORM_FIELDS, FORM_TITLES, fill_from_sections
from ..models import DocStatus, GeneratedDocument, Guide, SourceDocument, User
from ..schemas import UTCDateTime
from ..services.exporters.form_export import MEDIA, FormDoc, build_form_file

router = APIRouter(prefix="/api", tags=["규격서·견적서 생성"])

FormType = Literal["spec", "quote"]
_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|]')

class FormIn(BaseModel):
    doc_type: FormType
    title: str
    fields: dict[str, str]
    source_document_id: int | None = None  # 재사용한 등록 문서
    based_on_id: int | None = None  # 고쳐 만든 이전 생성 문서 (다음 버전이 된다)

class GeneratedOut(BaseModel):
    id: int
    doc_type: str
    title: str
    fields: dict[str, str]
    version: int
    root_id: int
    based_on_id: int | None
    source_document_id: int | None
    source_document_title: str | None
    created_by: int
    created_by_name: str
    partner_name: str | None
    created_at: UTCDateTime

def _out(g: GeneratedDocument) -> GeneratedOut:
    return GeneratedOut(
        id=g.id,
        doc_type=g.doc_type,
        title=g.title,
        fields=g.fields or {},
        version=g.version,
        root_id=g.root_id or g.id,
        based_on_id=g.based_on_id,
        source_document_id=g.source_document_id,
        source_document_title=g.source_document.title if g.source_document else None,
        created_by=g.created_by,
        created_by_name=g.creator.name,
        partner_name=g.partner.name if g.partner else None,
        created_at=g.created_at,
    )

def _clean(body: FormIn) -> dict[str, str]:
    """필수 입력 항목만 남기고, 비어 있으면 400."""
    values = {f["key"]: (body.fields.get(f["key"]) or "").strip() for f in FORM_FIELDS[body.doc_type]}
    missing = [f["label"] for f in FORM_FIELDS[body.doc_type] if not values[f["key"]]]
    if not body.title.strip():
        missing.insert(0, "문서 제목")
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"필수 입력 항목을 채우세요: {', '.join(missing)}")
    return values

def _form(doc_type: str, title: str, values: dict, meta: list[tuple[str, str]]) -> FormDoc:
    return FormDoc(kind=FORM_TITLES[doc_type], title=title, fields=FORM_FIELDS[doc_type], values=values, meta=meta)

def _get_generated(db: Session, user: User, generated_id: int) -> GeneratedDocument:
    """본인이 만든 것, 같은 조직이 만든 것, 관리자는 전부."""
    g = db.get(GeneratedDocument, generated_id)
    if g is None or not (is_admin(user) or g.created_by == user.id or (g.partner_id and g.partner_id == user.partner_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "생성한 문서를 찾을 수 없습니다.")
    return g

@router.get("/forms/{doc_type}/fields")
def form_fields(doc_type: FormType, _user: User = Depends(get_active_user)) -> list[dict]:
    """생성 화면의 필수 입력 항목."""
    return FORM_FIELDS[doc_type]

@router.get("/forms/{doc_type}/prefill")
def prefill(
    doc_type: FormType, document_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> dict:
    """재사용할 등록 문서의 내용으로 입력 항목을 채운다 (목차 제목이 항목 이름과 같으면 그 본문, 나머지는 순서대로)."""
    require_permission(db, user, doc_type)
    doc = get_readable_document(db, user, document_id)
    if doc.status != DocStatus.PARSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "문서 분석이 끝난 뒤에 재사용할 수 있습니다.")
    sections = [(s.title, s.text or "") for s in doc.sections]
    return {"title": doc.title or "", "fields": fill_from_sections(doc_type, sections)}

@router.post("/forms/preview")
def preview(body: FormIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> Response:
    """미리보기 PDF (저장하지 않는다). 비어 있는 항목도 그대로 보여 준다."""
    require_permission(db, user, body.doc_type)
    values = {f["key"]: (body.fields.get(f["key"]) or "").strip() for f in FORM_FIELDS[body.doc_type]}
    meta = [("작성자", user.name), ("소속", user.partner.name if user.partner else "-"), ("상태", "미리보기")]
    pdf = build_form_file(_form(body.doc_type, body.title.strip() or "(제목 없음)", values, meta), "pdf")
    return Response(pdf, media_type=MEDIA["pdf"], headers={"Content-Disposition": "inline; filename=preview.pdf"})

@router.post("/generated", response_model=GeneratedOut, status_code=status.HTTP_201_CREATED)
def create_generated(body: FormIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> GeneratedOut:
    """생성: 입력값을 저장한다. 이전 생성 문서를 고쳐 만들면 그 문서의 다음 버전이 된다."""
    require_permission(db, user, body.doc_type)
    values = _clean(body)
    if body.source_document_id is not None:
        get_readable_document(db, user, body.source_document_id)
    g = GeneratedDocument(
        doc_type=body.doc_type,
        title=body.title.strip(),
        fields=values,
        source_document_id=body.source_document_id,
        partner_id=user.partner_id,
        created_by=user.id,
    )
    if body.based_on_id is not None:
        base = _get_generated(db, user, body.based_on_id)
        if base.doc_type != body.doc_type:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "다른 종류의 문서로는 새 버전을 만들 수 없습니다.")
        root = base.root_id or base.id
        latest = db.scalar(
            select(func.max(GeneratedDocument.version)).where(or_(GeneratedDocument.root_id == root, GeneratedDocument.id == root))
        )
        g.root_id, g.based_on_id, g.version = root, base.id, (latest or 1) + 1
        g.source_document_id = g.source_document_id or base.source_document_id
    db.add(g)
    db.commit()
    db.refresh(g)
    return _out(g)

@router.get("/generated", response_model=list[GeneratedOut])
def list_generated(
    doc_type: FormType, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> list[GeneratedOut]:
    """생성한 ○○: 내가 만든 문서의 모든 버전 (관리자는 전체). 최신이 먼저."""
    query = select(GeneratedDocument).where(GeneratedDocument.doc_type == doc_type).order_by(GeneratedDocument.created_at.desc())
    if not is_admin(user):
        query = query.where(GeneratedDocument.created_by == user.id)
    return [_out(g) for g in db.scalars(query)]

@router.get("/generated/{generated_id}", response_model=GeneratedOut)
def get_generated(generated_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> GeneratedOut:
    return _out(_get_generated(db, user, generated_id))

@router.get("/generated/{generated_id}/download")
def download_generated(
    generated_id: int,
    format: Literal["pdf", "docx"] = Query("pdf"),
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
    data = build_form_file(_form(g.doc_type, g.title, g.fields or {}, meta), format)
    name = f"{_UNSAFE_NAME.sub('_', g.title)[:100]}_v{g.version}.{format}"

    return Response(data, media_type=MEDIA[format], headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote(name)}"})

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
