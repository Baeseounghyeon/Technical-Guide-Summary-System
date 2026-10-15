from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_active_user, get_guide_for_user, is_admin
from ..models import Export, ExportStatus, Guide, GuideStatus, JobKind, Partner, User
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

    partner_id = body.partner_id or guide.document.partner_id
    if partner_id is not None and not is_admin(user) and partner_id != user.partner_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "다른 파트너사의 로고·양식은 쓸 수 없습니다.")
    partner = db.get(Partner, partner_id) if partner_id else None
    if partner_id and partner is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "파트너사를 찾을 수 없습니다.")
    if body.use_partner_template:
        template = (partner.docx_template_path if body.format == "docx" else partner.pptx_template_path) if partner else None
        if not template:
            kind = "Word" if body.format == "docx" else "PowerPoint"
            raise HTTPException(status.HTTP_400_BAD_REQUEST, f"선택한 파트너사에 등록된 {kind} 양식이 없습니다. 먼저 양식을 올려 주세요.")
    if body.include_logo and not (partner and partner.logo_path):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "선택한 파트너사에 등록된 로고가 없습니다.")

    export = Export(
        guide=guide,
        partner_id=partner_id,
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
    try:
        guide = get_guide_for_user(db, user, export.guide_id)
    except HTTPException:
        # 다른 파트너사 가이드: 소유 파트너사가 다운로드 요청을 승인했으면 받을 수 있다.
        from .sharing import can_download_shared

        guide = db.get(Guide, export.guide_id)
        if guide is None or not can_download_shared(db, user, guide):
            raise
    if export.status != ExportStatus.DONE or not export.file_path:
        raise HTTPException(status.HTTP_409_CONFLICT, "아직 생성되지 않은 문서입니다.")
    title = guide.document.title or "guide"
    return FileResponse(
        export.file_path,
        media_type=MEDIA_TYPES[export.format],
        filename=f"{title}_{guide.target_language}_v{export.doc_version}.{export.format}",
    )
