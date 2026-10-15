from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_active_user, get_guide_for_user
from ..models import Export, ExportStatus, GuideStatus, JobKind, User
from ..schemas import ExportCreate, ExportOut
from ..services.jobs import enqueue

router = APIRouter(prefix="/api", tags=["최종 문서"])

MEDIA_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


@router.post("/guides/{guide_id}/exports", response_model=ExportOut, status_code=status.HTTP_201_CREATED)
def create_export(
    guide_id: int, body: ExportCreate, user: User = Depends(get_active_user), db: Session = Depends(get_db)
) -> Export:
    guide = get_guide_for_user(db, user, guide_id)
    # 피드백 필수: 모든 목차 항목이 승인되어야 최종 문서를 만들 수 있다.
    if guide.status != GuideStatus.APPROVED:
        raise HTTPException(status.HTTP_409_CONFLICT, "모든 목차 항목을 승인한 뒤에 문서를 생성할 수 있습니다.")
    export = Export(
        guide=guide,
        format=body.format,
        doc_version=body.doc_version,
        include_logo=body.include_logo,
        use_partner_template=body.use_partner_template,
        revision=body.revision.model_dump() if body.revision else None,
        created_by=user.id,
    )
    db.add(export)
    db.flush()
    enqueue(db, JobKind.EXPORT_GUIDE, {"export_id": export.id})
    db.commit()
    return export


@router.get("/guides/{guide_id}/exports", response_model=list[ExportOut])
def list_exports(guide_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[Export]:
    return get_guide_for_user(db, user, guide_id).exports


@router.get("/exports/{export_id}/download")
def download_export(export_id: int, user: User = Depends(get_active_user), db: Session = Depends(get_db)):
    export = db.get(Export, export_id)
    if export is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "문서를 찾을 수 없습니다.")
    guide = get_guide_for_user(db, user, export.guide_id)
    if export.status != ExportStatus.DONE or not export.file_path:
        raise HTTPException(status.HTTP_409_CONFLICT, "아직 생성되지 않은 문서입니다.")
    title = guide.document.title or "guide"
    return FileResponse(
        export.file_path,
        media_type=MEDIA_TYPES[export.format],
        filename=f"{title}_{guide.target_language}_v{export.doc_version}.{export.format}",
    )
