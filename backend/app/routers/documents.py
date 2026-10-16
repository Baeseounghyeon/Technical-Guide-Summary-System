import re
import tempfile
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import (
    needs,
    require_permission,
    accessible_vendors,
    ensure_vendor_access,
    get_active_user,
    document_access,
    get_document_for_user,
    get_readable_document,
    granted_vendor_ids,
    is_admin,
    require_platform_admin,
)
from ..catalog import PRODUCT_CATALOG, validate_product
from ..models import DocStatus, DocType, DocumentShare, GuideKind, JobKind, Partner, Section, SourceDocument, User, Vendor, utcnow
from ..schemas import UTCDateTime
from ..schemas import DocumentDetail, DocumentOut, GuideBrief, SectionOut, SectionPatch
from ..services.jobs import enqueue
from ..services.exporters.document_export import MEDIA_TYPES, build_document_file, doc_info
from ..services.parsing import SUPPORTED_EXTENSIONS
from ..services.storage import get_storage
from .uploads import store_upload

router = APIRouter(prefix="/api", tags=["원본 문서"])


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def create_document(
    vendor_id: int = Form(...),
    title: str | None = Form(None),
    doc_type: Literal["spec", "guide", "brochure"] = Form("guide"),
    guide_kind: Literal["technical", "troubleshooting"] = Form("technical"),
    product: str | None = Form(None),
    product_detail: str | None = Form(None),
    description: str | None = Form(None),
    url: str | None = Form(None),
    file: UploadFile | None = File(None),
    storage_key: str | None = Form(None),
    filename: str | None = Form(None),
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> DocumentOut:
    """파일(PDF/Word/PPT) 또는 웹 문서 URL을 등록하고 파싱 작업을 예약한다."""
    ensure_vendor_access(db, user, vendor_id)
    require_permission(db, user, doc_type)  # 엔지니어: 가이드·브로슈어 / 영업: 규격서·브로슈어 (+ 승인된 추가 권한)
    product, product_detail = (product or "").strip() or None, (product_detail or "").strip() or None
    vendor = db.get(Vendor, vendor_id)
    if error := validate_product(vendor.name, product, product_detail):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, error)
    has_file = file is not None or bool(storage_key)
    if has_file == bool(url):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "파일 또는 URL 중 하나만 입력하세요.")

    doc = SourceDocument(
        vendor_id=vendor_id,
        partner_id=user.partner_id,
        uploaded_by=user.id,
        title=title or None,
        doc_type=doc_type,
        guide_kind=guide_kind if doc_type == DocType.GUIDE else None,
        product=product,
        product_detail=product_detail,
        description=(description or "").strip() or None,
    )
    if has_file:
        ext = Path(file.filename or "" if file is not None else storage_key).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "PDF, Word(.docx), PowerPoint(.pptx) 파일만 지원합니다."
            )
        ref, original_name = store_upload("uploads", file, storage_key, filename)
        doc.source_type = SUPPORTED_EXTENSIONS[ext]
        doc.file_path = ref
        fallback_title = Path(original_name).stem
    else:
        doc.source_type = "url"
        doc.url = url
        fallback_title = url

    db.add(doc)
    db.flush()
    # 제목 우선순위: 사용자 입력 > 문서 메타데이터 제목 > 파일명(URL)
    enqueue(db, JobKind.PARSE_DOCUMENT, {"document_id": doc.id, "fallback_title": fallback_title})
    db.commit()
    return _document_out(doc)


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
    vendor_id: int | None = None,
    doc_type: Literal["spec", "guide", "brochure"] | None = None,
    guide_kind: Literal["technical", "troubleshooting"] | None = None,
    partner_id: int | None = None,
    uploaded_by: int | None = None,
    product: str | None = None,
    product_detail: str | None = None,
    shared_to_me: bool = False,
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    """내가 볼 수 있는 문서: 내 조직 문서 + 내 조직에 공유된 문서 + 도메인 권한이 승인된 벤더의 문서.
    shared_to_me=true 면 다른 조직이 내 조직에 공유한 문서만."""
    query = select(SourceDocument).where(SourceDocument.deleted_at.is_(None)).order_by(SourceDocument.created_at.desc())
    if product:
        query = query.where(SourceDocument.product == product)
    if product_detail:
        query = query.where(SourceDocument.product_detail == product_detail)
    shared_ids = select(DocumentShare.document_id).where(DocumentShare.partner_id == user.partner_id)
    if shared_to_me:
        query = query.where(SourceDocument.id.in_(shared_ids), SourceDocument.partner_id.is_distinct_from(user.partner_id))
    elif not is_admin(user):
        vendor_ids = [v.id for v in accessible_vendors(db, user)]
        query = query.where(
            or_(
                (SourceDocument.partner_id == user.partner_id) & SourceDocument.vendor_id.in_(vendor_ids),
                SourceDocument.id.in_(shared_ids),
                SourceDocument.vendor_id.in_(granted_vendor_ids(db, user) or {-1}),
            )
        )
    if vendor_id is not None:
        query = query.where(SourceDocument.vendor_id == vendor_id)
    if doc_type == DocType.GUIDE:
        # 종류가 생기기 전에 올린 문서는 기술 가이드로 본다
        query = query.where(or_(SourceDocument.doc_type == DocType.GUIDE, SourceDocument.doc_type.is_(None)))
    elif doc_type is not None:
        query = query.where(SourceDocument.doc_type == doc_type)
    if partner_id is not None:
        query = query.where(SourceDocument.partner_id == partner_id)
    if uploaded_by is not None:
        query = query.where(SourceDocument.uploaded_by == uploaded_by)
    if guide_kind == GuideKind.TECHNICAL:
        query = query.where(or_(SourceDocument.guide_kind == GuideKind.TECHNICAL, SourceDocument.guide_kind.is_(None)))
    elif guide_kind is not None:
        query = query.where(SourceDocument.guide_kind == guide_kind)
    return [_document_out(d, document_access(db, user, d) or "own") for d in db.scalars(query)]


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> DocumentDetail:
    doc = get_readable_document(db, user, document_id)
    return DocumentDetail(
        **_document_out(doc, document_access(db, user, doc) or "own").model_dump(),
        sections=[_section_out(s) for s in doc.sections],
        guides=[GuideBrief.model_validate(g) for g in doc.guides],
    )


@router.patch("/sections/{section_id}", response_model=SectionOut, dependencies=[Depends(needs("guide"))])
def update_section(
    section_id: int, body: SectionPatch, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> SectionOut:
    """목차 확인 단계: 요약 대상 포함/제외."""
    section = db.get(Section, section_id)
    if section is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "목차 항목을 찾을 수 없습니다.")
    get_document_for_user(db, user, section.document_id)
    section.included = body.included
    db.commit()
    return _section_out(section)


def _document_out(doc: SourceDocument, access: str = "own") -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        vendor_id=doc.vendor_id,
        vendor_name=doc.vendor.name,
        title=doc.title,
        doc_type=doc.doc_type or DocType.GUIDE,
        guide_kind=(doc.guide_kind or GuideKind.TECHNICAL) if (doc.doc_type or DocType.GUIDE) == DocType.GUIDE else None,
        product=doc.product,
        product_detail=doc.product_detail,
        description=doc.description,
        partner_id=doc.partner_id,
        partner_name=doc.partner.name if doc.partner else None,
        uploaded_by=doc.uploaded_by,
        uploaded_by_name=doc.uploader.name if doc.uploader else None,
        access=access,
        shared_with=sorted(s.partner.name for s in doc.shares),
        source_type=doc.source_type,
        url=doc.url,
        page_count=doc.page_count,
        status=doc.status,
        error=doc.error,
        created_at=doc.created_at,
    )


def _section_out(s: Section) -> SectionOut:
    return SectionOut(
        id=s.id,
        parent_id=s.parent_id,
        order_index=s.order_index,
        level=s.level,
        title=s.title,
        page_start=s.page_start,
        page_end=s.page_end,
        included=s.included,
        char_count=len(s.text),
    )


DOC_TYPE_LABELS = {"spec": "규격서", "guide": "가이드", "brochure": "브로슈어"}
DownloadFormat = Literal["original", "docx", "pptx", "xlsx", "pdf"]
_UNSAFE_NAME = re.compile(r'[\\/:*?"<>|]')  # 파일 이름에 쓸 수 없는 문자


@router.get("/documents/{document_id}/download")
def download_document(
    document_id: int,
    format: DownloadFormat = Query("original"),
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> Response:
    """원본 파일 그대로, 또는 분석한 목차별 본문으로 Word·PowerPoint·Excel·PDF 를 만들어 내려받는다."""
    doc = get_readable_document(db, user, document_id)
    storage = get_storage()
    base = _UNSAFE_NAME.sub("_", doc.title or f"document{doc.id}")[:120]
    original_ext = Path(doc.file_path).suffix.lower() if doc.file_path else ""
    # PDF 원본에 PDF 를 고르면 원본을 그대로 준다 (서식이 그대로 남음).
    if format == "original" or (format == "pdf" and original_ext == ".pdf"):
        if not doc.file_path:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "웹 주소로 등록한 문서는 원본 파일이 없습니다. 다른 형식을 고르세요.")
        return storage.response(doc.file_path, f"{base}{original_ext}", "application/octet-stream")
    if doc.status != DocStatus.PARSED:
        raise HTTPException(status.HTTP_409_CONFLICT, "문서 분석이 끝난 뒤에 다른 형식으로 받을 수 있습니다.")
    info = doc_info(doc, DOC_TYPE_LABELS.get(doc.doc_type or "guide", "문서"))
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / f"doc{doc.id}.{format}"
        build_document_file(info, format, out)
        ref = storage.save(f"downloads/doc{doc.id}_{format}.{format}", out.read_bytes())
    return storage.response(ref, f"{base}.{format}", MEDIA_TYPES[format])


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> None:
    """같은 조직(파트너사) 사람이나 관리자: 문서를 휴지통으로 옮긴다. 휴지통에서 복구하면 그대로 돌아온다."""
    doc = get_readable_document(db, user, document_id)
    if not can_trash(user, doc):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "같은 조직의 문서만 삭제할 수 있습니다.")
    doc.deleted_at, doc.deleted_by = utcnow(), user.id
    db.commit()


def can_trash(user: User, doc: SourceDocument) -> bool:
    """삭제·복구: 관리자, 또는 문서가 내 조직 것일 때 (공유받거나 도메인 열람으로 보는 문서는 불가)."""
    return is_admin(user) or (doc.partner_id is not None and doc.partner_id == user.partner_id)


# ---------- 휴지통 ----------


class TrashItem(BaseModel):
    id: int
    title: str | None
    doc_type: str
    vendor_name: str
    product: str | None
    product_detail: str | None
    uploaded_by_name: str | None
    created_at: UTCDateTime
    deleted_by_name: str | None
    deleted_at: UTCDateTime


@router.get("/trash", response_model=list[TrashItem])
def list_trash(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[TrashItem]:
    """내 조직의 삭제된 문서 (관리자는 전체). 최근에 지운 것부터."""
    query = select(SourceDocument).where(SourceDocument.deleted_at.is_not(None)).order_by(SourceDocument.deleted_at.desc())
    if not is_admin(user):
        query = query.where(SourceDocument.partner_id == user.partner_id)
    return [
        TrashItem(
            id=d.id,
            title=d.title or d.url,
            doc_type=d.doc_type or DocType.GUIDE,
            vendor_name=d.vendor.name,
            product=d.product,
            product_detail=d.product_detail,
            uploaded_by_name=d.uploader.name if d.uploader else None,
            created_at=d.created_at,
            deleted_by_name=d.deleter.name if d.deleter else None,
            deleted_at=d.deleted_at,
        )
        for d in db.scalars(query)
    ]


@router.post("/trash/{document_id}/restore", response_model=DocumentOut)
def restore_document(document_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> DocumentOut:
    """휴지통에서 복구: 삭제 표시만 지우므로 등록일·목차·요약 가이드가 삭제 전 그대로 돌아온다 (목록에서도 원래 자리)."""
    doc = db.get(SourceDocument, document_id)
    if doc is None or doc.deleted_at is None or not can_trash(user, doc):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "휴지통에 그 문서가 없습니다.")
    doc.deleted_at, doc.deleted_by = None, None
    db.commit()
    return _document_out(doc, document_access(db, user, doc) or "own")


@router.get("/catalog")
def product_catalog(_user: User = Depends(get_active_user)) -> dict:
    """벤더별 제품군·상세 목록."""
    return PRODUCT_CATALOG



# ---------- 가이드 공유: 문서를 공유할 조직 ----------


class ShareIn(BaseModel):
    partner_ids: list[int]


@router.get("/organizations")
def list_organizations(_user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[dict]:
    """공유 범위로 고를 수 있는 조직(파트너사) 목록 (이름만)."""
    return [{"id": p.id, "name": p.name} for p in db.scalars(select(Partner).order_by(Partner.name))]


@router.put("/documents/{document_id}/shares", response_model=DocumentOut)
def set_shares(document_id: int, body: ShareIn, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> DocumentOut:
    """문서를 공유할 조직을 정한다 (여러 개). 문서를 올린 사람이나 관리자만."""
    doc = get_readable_document(db, user, document_id)
    if not (is_admin(user) or doc.uploaded_by == user.id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "문서를 올린 사람이나 관리자만 공유 범위를 정할 수 있습니다.")
    wanted = set(body.partner_ids) - ({doc.partner_id} if doc.partner_id else set())  # 내 조직은 원래 볼 수 있음
    found = {p.id for p in db.scalars(select(Partner).where(Partner.id.in_(wanted)))} if wanted else set()
    if found != wanted:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "없는 조직이 포함되어 있습니다.")
    doc.shares = [s for s in doc.shares if s.partner_id in wanted]
    have = {s.partner_id for s in doc.shares}
    doc.shares += [DocumentShare(partner_id=pid) for pid in sorted(wanted - have)]
    db.commit()
    db.refresh(doc)
    return _document_out(doc, document_access(db, user, doc) or "own")
