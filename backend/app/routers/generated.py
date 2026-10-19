"""규격서·견적서 생성: 필수 입력 항목을 채워(재사용할 문서에서 가져와 고칠 수도 있음) PDF·Word 로 만든다.
규격서는 문서 등록에서 올린 제품 가격표·매입 금액 문서를 하나씩 골라 첨부할 수 있다.
생성 기록은 버전별로 남아 '생성한 ○○'에서 이력을 본다. 생성한 가이드(요약 가이드) 목록도 여기서 준다."""

import re
from typing import Literal
from urllib.parse import quote

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
from ..services.exporters.form_export import FormDoc, build_form_file
from ..services.exporters.quote_export import MEDIA

router = APIRouter(prefix="/api", tags=["규격서·견적서 생성"])

FormType = Literal["spec", "quote"]
_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|]')
# 규격서 생성 때 첨부로 가져오는 문서 종류 (문서 등록의 제품 가격표·매입 금액)
EXTRA_KINDS = {"price_list": "제품 가격표", "purchase": "매입 금액"}


class FormIn(BaseModel):
    doc_type: FormType
    title: str
    fields: dict[str, str]
    source_document_id: int | None = None  # 재사용한 등록 문서
    based_on_id: int | None = None  # 고쳐 만든 이전 생성 문서 (다음 버전이 된다)
    attachments: dict[str, int | None] = {}  # {"price_list": 문서 id, "purchase": 문서 id} (규격서만)


class AttachmentOut(BaseModel):
    kind: str  # price_list | purchase
    label: str  # 제품 가격표 | 매입 금액
    document_id: int
    title: str | None


class GeneratedOut(BaseModel):
    id: int
    doc_type: str
    title: str
    fields: dict  # 규격서: 항목 값 / 견적서: 양식·항목 표·작성자
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
        doc_id = (ids or {}).get(kind)
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


def _clean(body: FormIn) -> dict[str, str]:
    """필수 입력 항목만 남기고, 비어 있으면 400."""
    values = {f["key"]: (body.fields.get(f["key"]) or "").strip() for f in FORM_FIELDS[body.doc_type]}
    missing = [f["label"] for f in FORM_FIELDS[body.doc_type] if not values[f["key"]]]
    if not body.title.strip():
        missing.insert(0, "문서 제목")
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"필수 입력 항목을 채우세요: {', '.join(missing)}")
    return values


def _check_attachments(db: Session, user: User, body: FormIn) -> dict[str, int]:
    """첨부로 고른 문서가 그 종류의 기타 문서이고 볼 수 있는 문서인지 확인한다."""
    picked = {k: v for k, v in body.attachments.items() if v}
    if picked and body.doc_type != "spec":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "제품 가격표·매입 금액 첨부는 규격서에서만 합니다. 견적서는 견적서 생성 단계에서 고르세요.")
    for kind, doc_id in picked.items():
        if kind not in EXTRA_KINDS:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"알 수 없는 첨부 종류입니다: {kind}")
        doc = get_readable_document(db, user, doc_id)
        if doc.doc_type != kind:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{EXTRA_KINDS[kind]}(으)로 등록한 문서를 고르세요.")
    return picked


def _form(db: Session, doc_type: str, title: str, values: dict, meta: list[tuple[str, str]], attachments: dict | None) -> FormDoc:
    return FormDoc(
        kind=FORM_TITLES[doc_type],
        title=title,
        fields=FORM_FIELDS[doc_type],
        values=values,
        meta=meta,
        attachments=[(EXTRA_KINDS[k], d.title or f"문서 {d.id}") for k, d in _attachment_docs(db, attachments)],
    )


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
    attachments = _check_attachments(db, user, body)
    values = {f["key"]: (body.fields.get(f["key"]) or "").strip() for f in FORM_FIELDS[body.doc_type]}
    meta = [("작성자", user.name), ("소속", user.partner.name if user.partner else "-"), ("상태", "미리보기")]
    pdf = build_form_file(_form(db, body.doc_type, body.title.strip() or "(제목 없음)", values, meta, attachments), "pdf")
    return Response(pdf, media_type=MEDIA["pdf"], headers={"Content-Disposition": "inline; filename=preview.pdf"})


@router.post("/generated", response_model=GeneratedOut, status_code=status.HTTP_201_CREATED)
def create_generated(body: FormIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> GeneratedOut:
    """생성: 입력값을 저장한다. 이전 생성 문서를 고쳐 만들면 그 문서의 다음 버전이 된다."""
    require_permission(db, user, body.doc_type)
    if body.doc_type == "quote":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "견적서는 견적서 생성 단계(/api/quote-builder)로 만듭니다.")
    values = _clean(body)
    attachments = _check_attachments(db, user, body)
    if body.source_document_id is not None:
        get_readable_document(db, user, body.source_document_id)
    g = GeneratedDocument(
        doc_type=body.doc_type,
        title=body.title.strip(),
        fields=values,
        attachments=attachments or None,
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
    return _out(db, g)


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
    if g.doc_type == "quote":
        data = _quote_file(db, user, g, format, meta)
    else:
        data = build_form_file(_form(db, g.doc_type, g.title, g.fields or {}, meta, g.attachments), format)
    name = f"{_UNSAFE_NAME.sub('_', g.title)[:100]}_v{g.version}.{format}"
    return Response(data, media_type=MEDIA[format], headers={"Content-Disposition": f"attachment; filename*=utf-8''{quote(name)}"})


def _quote_file(db: Session, user: User, g: GeneratedDocument, fmt: str, meta: list) -> bytes:
    """견적서 파일: 양식과 같은 형식이면 양식을 채우고, 아니면 기본 양식. 양식이 지워졌으면 기본 양식."""
    from ..models import QuoteTemplate
    from ..services.exporters.quote_export import build_quote
    from ..services.storage import get_storage
    from .quote_builder import quote_data

    fields = g.fields or {}
    data = quote_data(fields, version=f"v{g.version}", date=f"{g.created_at:%Y-%m-%d}", meta=meta)
    template = db.get(QuoteTemplate, fields["template_id"]) if fields.get("template_id") else None
    if template is None:
        return build_quote(data, fmt, None, None)
    with get_storage().local_path(template.file_path) as path:
        return build_quote(data, fmt, path, template.file_ext)


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
