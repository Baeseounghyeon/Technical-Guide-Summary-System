import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..deps import accessible_vendors, ensure_vendor_access, get_active_user, get_document_for_user, is_admin
from ..models import JobKind, Section, SourceDocument, User
from ..schemas import DocumentDetail, DocumentOut, GuideBrief, SectionOut, SectionPatch
from ..services.jobs import enqueue
from ..services.parsing import SUPPORTED_EXTENSIONS

router = APIRouter(prefix="/api", tags=["원본 문서"])


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def create_document(
    vendor_id: int = Form(...),
    title: str | None = Form(None),
    url: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> DocumentOut:
    """파일(PDF/Word/PPT) 또는 웹 문서 URL을 등록하고 파싱 작업을 예약한다."""
    ensure_vendor_access(db, user, vendor_id)
    if (file is None) == (not url):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "파일 또는 URL 중 하나만 입력하세요.")

    doc = SourceDocument(vendor_id=vendor_id, partner_id=user.partner_id, uploaded_by=user.id, title=title or None)
    if file is not None:
        ext = Path(file.filename or "").suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "PDF, Word(.docx), PowerPoint(.pptx) 파일만 지원합니다."
            )
        upload_dir = settings.storage_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        path = upload_dir / f"{uuid.uuid4().hex}{ext}"
        with path.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        doc.source_type = SUPPORTED_EXTENSIONS[ext]
        doc.file_path = str(path)
        fallback_title = Path(file.filename or "").stem
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
    vendor_id: int | None = None, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> list[DocumentOut]:
    query = select(SourceDocument).order_by(SourceDocument.created_at.desc())
    if not is_admin(user):
        vendor_ids = [v.id for v in accessible_vendors(db, user)]
        query = query.where(SourceDocument.partner_id == user.partner_id, SourceDocument.vendor_id.in_(vendor_ids))
    if vendor_id is not None:
        query = query.where(SourceDocument.vendor_id == vendor_id)
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
