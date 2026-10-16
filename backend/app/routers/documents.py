from pathlib import Path

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import accessible_vendors, ensure_vendor_access, get_active_user, get_document_for_user, is_admin
from ..models import DocType, GuideKind, JobKind, Section, SourceDocument, User
from ..schemas import DocumentDetail, DocumentOut, GuideBrief, SectionOut, SectionPatch
from ..services.jobs import enqueue
from ..services.parsing import SUPPORTED_EXTENSIONS
from .uploads import store_upload

router = APIRouter(prefix="/api", tags=["원본 문서"])


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def create_document(
    vendor_id: int = Form(...),
    title: str | None = Form(None),
    doc_type: Literal["spec", "guide", "brochure"] = Form("guide"),
    guide_kind: Literal["technical", "troubleshooting"] = Form("technical"),
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
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    query = select(SourceDocument).order_by(SourceDocument.created_at.desc())
    if not is_admin(user):
        vendor_ids = [v.id for v in accessible_vendors(db, user)]
        query = query.where(SourceDocument.partner_id == user.partner_id, SourceDocument.vendor_id.in_(vendor_ids))
    if vendor_id is not None:
        query = query.where(SourceDocument.vendor_id == vendor_id)
    if doc_type == DocType.GUIDE:
        # 종류가 생기기 전에 올린 문서는 기술 가이드로 본다
        query = query.where(or_(SourceDocument.doc_type == DocType.GUIDE, SourceDocument.doc_type.is_(None)))
    elif doc_type is not None:
        query = query.where(SourceDocument.doc_type == doc_type)
    if guide_kind == GuideKind.TECHNICAL:
        query = query.where(or_(SourceDocument.guide_kind == GuideKind.TECHNICAL, SourceDocument.guide_kind.is_(None)))
    elif guide_kind is not None:
        query = query.where(SourceDocument.guide_kind == guide_kind)
    return [_document_out(d) for d in db.scalars(query)]


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> DocumentDetail:
    doc = get_document_for_user(db, user, document_id)
    return DocumentDetail(
        **_document_out(doc).model_dump(),
        sections=[_section_out(s) for s in doc.sections],
        guides=[GuideBrief.model_validate(g) for g in doc.guides],
    )


@router.patch("/sections/{section_id}", response_model=SectionOut)
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


def _document_out(doc: SourceDocument) -> DocumentOut:
    return DocumentOut(
        id=doc.id,
        vendor_id=doc.vendor_id,
        vendor_name=doc.vendor.name,
        title=doc.title,
        doc_type=doc.doc_type or DocType.GUIDE,
        guide_kind=(doc.guide_kind or GuideKind.TECHNICAL) if (doc.doc_type or DocType.GUIDE) == DocType.GUIDE else None,
        description=doc.description,
        uploaded_by_name=doc.uploader.name if doc.uploader else None,
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
