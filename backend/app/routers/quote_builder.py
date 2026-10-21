"""견적서 생성 (단계별) — 견적서_매핑정리.md 기준.

1 견적서 양식 선택 → 2 제품 가격표 선택(참고용) → 3 가격표 항목 체크 → 4 매입 견적 PDF 선택(여러 건) → 5 매입 라인 확인·수정
→ 6 작성자 정보(로그인한 사용자) → 7 최종 확인(수신처·프로젝트명·환율·목표 금액)·미리보기 → 생성(엑셀·PDF).
견적서 한 행 = 매입 견적 PDF 한 건. 기본 양식은 유니포인트 견적서 엑셀(services/unipoint_quote.py).
견적서 양식(Word·Excel)은 '가져오기 > 견적서 양식'에서 따로 등록·변경할 수 있다 (자리 표시를 채운다).
"""

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_vendors, get_active_user, get_readable_document, is_admin, require_permission
from ..models import GeneratedDocument, QuoteTemplate, User, utcnow
from ..schemas import UTCDateTime
from ..services.exporters import quote_export
from ..services import unipoint_quote as uq
from ..services.thales_pdf import PRICE_COLUMNS, parse_price_list, parse_purchase_quote
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
    """제품 가격표(제품 번호·제품명·설명·리스트 가격)와 매입 견적(머리 정보 + 라인)을 뽑는다. Thales 형식이 아니면 첫 표 그대로."""
    doc = get_readable_document(db, user, document_id)
    if not doc.file_path:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "파일로 등록한 문서만 항목을 뽑을 수 있습니다.")
    with get_storage().local_path(doc.file_path) as path:
        if doc.source_type == "pdf" and doc.doc_type == "price_list":
            rows = parse_price_list(path)
            if rows:
                return {"columns": PRICE_COLUMNS, "rows": rows}
        if doc.source_type == "pdf" and doc.doc_type == "purchase":
            parsed = parse_purchase_quote(path)
            if parsed["rows"]:
                return parsed
        return extract_items(path, doc.source_type)


# ---------- 견적서 미리보기·생성 ----------


class Items(BaseModel):
    columns: list[str] = []
    rows: list[list[str]] = []


class PurchaseIn(BaseModel):
    """매입 견적 PDF 한 건 = 견적서 한 행."""

    document_id: int
    meta: dict = {}  # quote_number, end_user, partner, quote_total
    rows: list[list[str]] = []  # thales_pdf.PURCHASE_COLUMNS 순서 (화면에서 고친 값)
    included: list[bool] = []  # 금액(N)에 넣을 라인
    main: int = 0  # 대표 라인 (품명·설명·시리얼·수량·계약 번호)


class Settings(BaseModel):
    exchange_rate: float = Field(1360, gt=0)  # O열
    multiplier: float = Field(2.3, gt=0)  # G = N × O × 배수
    discount_pct: float = Field(0, ge=0, le=100)
    target_total: float | None = Field(None, gt=0)  # P9 목표 공급가 합계 → 할인율 역산
    current_rate: float | None = Field(None, gt=0)  # P12 당시 환율 (직접 입력, 참고용)
    ref_amount_1: float | None = Field(None, gt=0)  # U14 참고 금액
    ref_amount_2: float | None = Field(None, gt=0)  # U15 참고 금액


# 견적서를 만드는 도메인(벤더 이름, 소문자). 사용자에게 부여된 도메인만 고를 수 있다.
QUOTE_DOMAINS = ("thales", "ahnlab")


class QuoteIn(BaseModel):
    vendor_id: int | None = None  # 견적서 도메인(Thales·Ahnlab). 고른 문서도 이 도메인 것이어야 한다
    title: str = ""  # B8 프로젝트명
    recipient: str = ""  # B7 ○○ 귀중
    date: str = ""  # H8 견적일자 YYYY-MM-DD (비우면 오늘)
    template_id: int | None = None
    price_list_id: int | None = None  # 참고용
    price: Items = Items()
    purchases: list[PurchaseIn] = []
    author: dict[str, str] = {}
    settings: Settings = Settings()
    based_on_id: int | None = None  # 이전에 만든 견적서를 고쳐 만들면 다음 버전


def _lines(payload: dict) -> tuple[list[dict], dict]:
    purchases = [
        uq.Purchase(rows=p.get("rows") or [], included=list(p.get("included") or []), main=int(p.get("main") or 0), meta=p.get("meta") or {})
        for p in payload.get("purchases") or []
    ]
    return uq.build_lines(purchases, uq.QuoteSettings(**(payload.get("settings") or {})))


def quote_doc(payload: dict, date: str | None = None) -> uq.QuoteDoc:
    lines, totals = _lines(payload)
    return uq.QuoteDoc(
        project=payload.get("title") or "",
        recipient=payload.get("recipient") or "",
        date=date or payload.get("date") or f"{utcnow():%Y-%m-%d}",
        author=dict(payload.get("author") or {}),
        lines=lines,
        totals=totals,
        settings=uq.QuoteSettings(**(payload.get("settings") or {})),
    )


def _legacy(q: uq.QuoteDoc, version: str) -> quote_export.QuoteData:
    """직접 올린 양식(Word·Excel 자리 표시)용 데이터. 품목 표는 {{품목표}} 자리에 들어간다."""
    cols = ["순번", "Product Number", "Product Name", "Product Description", "수량", "단위", "금액", "공급가", "할인율", "비고"]
    rows = [
        [str(l["no"]), l["product_number"], l["product_name"], l["description"], str(l["quantity"]), l["unit"],
         f"{l['amount']:,.0f}", f"{l['supply']:,.0f}", f"{l['discount'] * 100:.1f}%", l["note"]]
        for l in q.lines
    ]
    author = {**q.author, "company": q.author.get("company", "")}
    return quote_export.QuoteData(
        title=q.project, author=author, tables=[quote_export.ItemTable("견적 품목", cols, rows)], date=q.date, version=version
    )


def formats_for(template: QuoteTemplate | None) -> list[str]:
    return [template.file_ext, "pdf"] if template else ["xlsx", "pdf"]


def render(payload: dict, template: QuoteTemplate | None, fmt: str, *, version: str = "", date: str | None = None) -> bytes:
    """기본: 유니포인트 견적서 엑셀(+PDF). 올린 엑셀 양식이 같은 견적서 모양이면 그 표 안에 채우고,
    그 밖의 올린 양식(Word·Excel)은 자리 표시({{작성자}}·{{품목표}} 등)를 채운다."""
    q = quote_doc(payload, date)
    if template is None:
        return uq.build_pdf(q) if fmt == "pdf" else uq.build_xlsx(q)[0]
    with get_storage().local_path(template.file_path) as path:
        if template.file_ext == "xlsx" and uq.is_quote_form(path):
            return uq.build_pdf(q, path) if fmt == "pdf" else uq.build_xlsx(q, path)[0]
        if fmt == "pdf":
            return uq.build_pdf(q)
        return quote_export.build_quote(_legacy(q, version), fmt, path, template.file_ext)


def render_preview(payload: dict, template: QuoteTemplate | None) -> str:
    q = quote_doc(payload)
    if template is None:
        return uq.preview_html(*uq.build_xlsx(q))
    with get_storage().local_path(template.file_path) as path:
        if template.file_ext == "xlsx" and uq.is_quote_form(path):
            return uq.preview_html(*uq.build_xlsx(q, path))
        return quote_export.preview_html(_legacy(q, ""), path, template.file_ext)


def _domain(db: Session, user: User, vendor_id: int | None):
    """견적서 도메인: 사용자에게 부여된 Thales·Ahnlab 도메인만."""
    if vendor_id is None:
        return None
    vendor = next((v for v in accessible_vendors(db, user) if v.id == vendor_id), None)
    if vendor is None or vendor.name.strip().lower() not in QUOTE_DOMAINS:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "부여된 견적서 도메인(Thales·Ahnlab)이 아닙니다.")
    return vendor


def _payload(db: Session, user: User, body: QuoteIn) -> tuple[dict, QuoteTemplate | None]:
    template = get_template(db, user, body.template_id) if body.template_id else None
    vendor = _domain(db, user, body.vendor_id)

    def check(doc_id: int, doc_type: str, label: str) -> None:
        doc = get_readable_document(db, user, doc_id)
        if doc.doc_type != doc_type:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{label}(으)로 등록한 문서를 고르세요.")
        if vendor is not None and doc.vendor_id != vendor.id:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"{vendor.name} 도메인의 {label} 문서를 고르세요.")

    if body.price_list_id:
        check(body.price_list_id, "price_list", "제품 가격표")
    for p in body.purchases:
        check(p.document_id, "purchase", "매입 금액")
    payload = {
        "vendor_id": vendor.id if vendor else None,
        "domain": vendor.name if vendor else None,
        "title": body.title.strip(),
        "recipient": body.recipient.strip(),
        "date": body.date or f"{utcnow():%Y-%m-%d}",
        "template_id": template.id if template else None,
        "template_name": template.name if template else None,
        "template_ext": template.file_ext if template else None,
        "price_list_id": body.price_list_id,
        "price": body.price.model_dump(),
        "purchases": [p.model_dump() for p in body.purchases],
        "author": {k: (v or "").strip() for k, v in body.author.items()},
        "settings": body.settings.model_dump(),
    }
    lines, totals = _lines(payload)
    payload["lines"], payload["totals"] = lines, totals
    return payload, template


@router.post("/quote-builder/preview")
def preview_quote(body: QuoteIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> dict:
    """7단계 미리보기: 만들어질 견적서(고객용 인쇄 영역)를 HTML 로. 계산한 품목·합계(매입·GP 포함)도 돌려준다."""
    require_permission(db, user, "quote")
    payload, template = _payload(db, user, body)
    return {"html": render_preview(payload, template), "formats": formats_for(template), "lines": payload["lines"], "totals": payload["totals"]}


@router.post("/quote-builder", status_code=status.HTTP_201_CREATED)
def create_quote(body: QuoteIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> dict:
    """최종 생성: 내용을 저장한다(생성한 견적서 이력). 파일은 받을 때 고른 형식으로 만든다."""
    require_permission(db, user, "quote")
    payload, _template = _payload(db, user, body)
    missing = []
    if not payload["title"]:
        missing.append("프로젝트명")
    if not payload["recipient"]:
        missing.append("수신처")
    if not payload["lines"] or not any(any(p.included) for p in body.purchases):
        missing.append("매입 견적 라인")
    if not payload["author"].get("name"):
        missing.append("작성자")
    if missing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"다음을 채우세요: {', '.join(missing)}")
    g = GeneratedDocument(
        doc_type="quote",
        title=payload["title"],
        fields=payload,
        attachments={"price_list": body.price_list_id, "purchase": [p.document_id for p in body.purchases]},
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
