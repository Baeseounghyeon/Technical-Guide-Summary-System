"""견적서 생성 (단계별).

1 견적서 양식 선택 → 2 제품 가격표 선택 → 3 가격표 항목 체크·수정 → 4 매입 금액 선택 → 5 매입 항목 체크·수정
→ 6 작성자 정보(로그인한 사용자로 자동 채움) → 7 최종 확인·미리보기 → 생성(원하는 형식으로 받기).
견적서 양식은 '가져오기 > 견적서 양식'에서 조직별로 등록·변경한다 (문서 등록과 별개).
"""

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_active_user, get_readable_document, is_admin, require_permission
from ..models import GeneratedDocument, QuoteTemplate, User, utcnow
from ..schemas import UTCDateTime
from ..services.exporters.quote_export import ItemTable, QuoteData, formats_for, preview_html
from ..services.storage import get_storage
from ..services.table_extract import extract_items
from .generated import _get_generated, _out
from .uploads import store_upload

router = APIRouter(prefix="/api", tags=["견적서 생성"])

TEMPLATE_EXTENSIONS = {".docx": "docx", ".xlsx": "xlsx"}
ITEM_SOURCES = {"price_list": "제품 가격표", "purchase": "매입 금액"}


# ---------- 견적서 양식 ----------


class TemplateOut(BaseModel):
    id: int
    name: str
    file_name: str
    file_ext: str
    partner_name: str | None
    uploaded_by_name: str
    updated_at: UTCDateTime


def _template_out(t: QuoteTemplate) -> TemplateOut:
    return TemplateOut(
        id=t.id,
        name=t.name,
        file_name=t.file_name,
        file_ext=t.file_ext,
        partner_name=t.partner.name if t.partner else None,
        uploaded_by_name=t.uploader.name,
        updated_at=t.updated_at,
    )


def get_template(db: Session, user: User, template_id: int) -> QuoteTemplate:
    """내 조직 양식만 (관리자는 전부)."""
    t = db.get(QuoteTemplate, template_id)
    if t is None or not (is_admin(user) or (t.partner_id is not None and t.partner_id == user.partner_id)):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "견적서 양식을 찾을 수 없습니다.")
    return t


def _store_template(file: UploadFile | None, storage_key: str | None, filename: str | None) -> tuple[str, str, str]:
    stored = store_upload("quote-templates", file, storage_key, filename)
    if stored is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "양식 파일을 올리세요.")
    ref, name = stored
    ext = TEMPLATE_EXTENSIONS.get(Path(name).suffix.lower())
    if ext is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "견적서 양식은 Word(.docx) 또는 Excel(.xlsx) 파일만 올릴 수 있습니다.")
    return ref, name, ext


@router.get("/quote-templates", response_model=list[TemplateOut])
def list_templates(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[TemplateOut]:
    query = select(QuoteTemplate).order_by(QuoteTemplate.updated_at.desc())
    if not is_admin(user):
        query = query.where(QuoteTemplate.partner_id == user.partner_id)
    return [_template_out(t) for t in db.scalars(query)]


@router.post("/quote-templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
def create_template(
    name: str = Form(...),
    file: UploadFile | None = File(None),
    storage_key: str | None = Form(None),
    filename: str | None = Form(None),
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> TemplateOut:
    require_permission(db, user, "quote")
    ref, original, ext = _store_template(file, storage_key, filename)
    t = QuoteTemplate(
        partner_id=user.partner_id, name=name.strip() or Path(original).stem, file_path=ref, file_name=original, file_ext=ext, uploaded_by=user.id
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _template_out(t)


@router.put("/quote-templates/{template_id}", response_model=TemplateOut)
def update_template(
    template_id: int,
    name: str | None = Form(None),
    file: UploadFile | None = File(None),
    storage_key: str | None = Form(None),
    filename: str | None = Form(None),
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> TemplateOut:
    """양식 변경: 이름이나 파일을 바꾼다."""
    require_permission(db, user, "quote")
    t = get_template(db, user, template_id)
    if name is not None and name.strip():
        t.name = name.strip()
    if file is not None or storage_key:
        t.file_path, t.file_name, t.file_ext = _store_template(file, storage_key, filename)
    t.updated_at = utcnow()
    db.commit()
    db.refresh(t)
    return _template_out(t)


@router.delete("/quote-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> None:
    require_permission(db, user, "quote")
    db.delete(get_template(db, user, template_id))
    db.commit()


@router.get("/quote-templates/{template_id}/download")
def download_template(template_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    t = get_template(db, user, template_id)
    return get_storage().response(t.file_path, t.file_name, "application/octet-stream")


# ---------- 문서 항목 뽑기 (3·5단계) ----------


@router.get("/documents/{document_id}/items")
def document_items(document_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> dict:
    """제품 가격표·매입 금액 문서의 표를 {columns, rows} 로 돌려준다."""
    doc = get_readable_document(db, user, document_id)
    if not doc.file_path:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "파일로 등록한 문서만 항목을 뽑을 수 있습니다.")
    with get_storage().local_path(doc.file_path) as path:
        return extract_items(path, doc.source_type)


# ---------- 견적서 미리보기·생성 ----------


class Items(BaseModel):
    columns: list[str] = []
    rows: list[list[str]] = []


class QuoteIn(BaseModel):
    title: str = ""
    template_id: int | None = None
    price_list_id: int | None = None
    price: Items = Items()
    purchase_id: int | None = None
    purchase: Items = Items()
    author: dict[str, str] = {}
    based_on_id: int | None = None  # 이전에 만든 견적서를 고쳐 만들면 다음 버전


def quote_data(q: dict, *, version: str = "", date: str | None = None, meta: list | None = None) -> QuoteData:
    """저장된 견적서 내용(fields) → 출력용 데이터."""
    tables = []
    for key, label in ITEM_SOURCES.items():
        items = (q.get("items") or {}).get(key) or {}
        if items.get("rows"):
            tables.append(ItemTable(label, list(items.get("columns") or []), [list(r) for r in items["rows"]]))
    return QuoteData(
        title=q.get("title") or "(제목 없음)",
        author=dict(q.get("author") or {}),
        tables=tables,
        date=date or f"{utcnow():%Y-%m-%d}",
        version=version,
        meta=meta or [],
    )


def _payload(db: Session, user: User, body: QuoteIn) -> tuple[dict, QuoteTemplate | None]:
    template = get_template(db, user, body.template_id) if body.template_id else None
    for doc_id, kind in ((body.price_list_id, "price_list"), (body.purchase_id, "purchase")):
        if doc_id:
            doc = get_readable_document(db, user, doc_id)
            if doc.doc_type != kind:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{ITEM_SOURCES[kind]}(으)로 등록한 문서를 고르세요.")
    payload = {
        "title": body.title.strip(),
        "template_id": template.id if template else None,
        "template_name": template.name if template else None,
        "template_ext": template.file_ext if template else None,
        "items": {"price_list": body.price.model_dump(), "purchase": body.purchase.model_dump()},
        "author": {k: (v or "").strip() for k, v in body.author.items()},
    }
    return payload, template


def render_preview(db: Session, payload: dict, template: QuoteTemplate | None) -> str:
    data = quote_data(payload, meta=[("상태", "미리보기")])
    if template is None:
        return preview_html(data, None, None)
    with get_storage().local_path(template.file_path) as path:
        return preview_html(data, path, template.file_ext)


@router.post("/quote-builder/preview")
def preview_quote(body: QuoteIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> dict:
    """7단계 미리보기: 실제로 만들어질 견적서(양식이 있으면 양식을 채운 결과)를 HTML 로."""
    require_permission(db, user, "quote")
    payload, template = _payload(db, user, body)
    return {"html": render_preview(db, payload, template), "formats": formats_for(template.file_ext if template else None)}


@router.post("/quote-builder", status_code=status.HTTP_201_CREATED)
def create_quote(body: QuoteIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> dict:
    """최종 생성: 내용을 저장한다(생성한 견적서 이력). 파일은 받을 때 원하는 형식으로 만든다."""
    require_permission(db, user, "quote")
    payload, _template = _payload(db, user, body)
    missing = []
    if not payload["title"]:
        missing.append("견적서 제목")
    if not body.price_list_id or not body.price.rows:
        missing.append("제품 가격표 항목")
    if not body.purchase_id or not body.purchase.rows:
        missing.append("매입 금액 항목")
    if not payload["author"].get("name"):
        missing.append("작성자")
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"다음을 채우세요: {', '.join(missing)}")
    g = GeneratedDocument(
        doc_type="quote",
        title=payload["title"],
        fields=payload,
        attachments={"price_list": body.price_list_id, "purchase": body.purchase_id},
        partner_id=user.partner_id,
        created_by=user.id,
    )
    if body.based_on_id is not None:
        base = _get_generated(db, user, body.based_on_id)
        root = base.root_id or base.id
        latest = db.scalar(
            select(func.max(GeneratedDocument.version)).where(or_(GeneratedDocument.root_id == root, GeneratedDocument.id == root))
        )
        g.root_id, g.based_on_id, g.version = root, base.id, (latest or 1) + 1
    db.add(g)
    db.commit()
    db.refresh(g)
    return _out(db, g).model_dump(mode="json")
