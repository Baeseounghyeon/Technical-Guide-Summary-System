from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field


def _as_utc(value: datetime) -> datetime:
    # SQLite 는 시간대 정보를 저장하지 않으므로 UTC 로 저장된 값에 시간대를 다시 붙인다.
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


UTCDateTime = Annotated[datetime, AfterValidator(_as_utc)]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- 인증 / 사용자 ----


class SignupIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=100)
    company_name: str = Field(min_length=1, max_length=200)
    department: str | None = None
    phone: str | None = None


class LoginIn(BaseModel):
    email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VendorOut(ORM):
    id: int
    name: str
    description: str | None = None


class UserOut(ORM):
    id: int
    email: str
    name: str
    phone: str | None
    department: str | None
    company_name: str | None
    role: str
    status: str
    partner_id: int | None
    created_at: UTCDateTime


class MeOut(UserOut):
    partner_name: str | None
    vendors: list[VendorOut]


class ApproveIn(BaseModel):
    partner_id: int | None = None
    role: Literal["platform_admin", "partner_admin", "engineer"] = "engineer"


# ---- 파트너 / 벤더 ----


class PartnerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class PartnerOut(ORM):
    id: int
    name: str
    logo_path: str | None
    docx_template_path: str | None
    pptx_template_path: str | None
    vendors: list[VendorOut]


class PartnerVendorsIn(BaseModel):
    vendor_ids: list[int]


class VendorIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None


class GlossaryTermIn(BaseModel):
    target_language: str
    source_term: str = Field(min_length=1, max_length=200)
    target_term: str = Field(min_length=1, max_length=200)


class GlossaryTermOut(ORM):
    id: int
    target_language: str
    source_term: str
    target_term: str


# ---- 원본 문서 ----


class SectionOut(ORM):
    id: int
    parent_id: int | None
    order_index: int
    level: int
    title: str
    page_start: int | None
    page_end: int | None
    included: bool
    char_count: int


class SectionPatch(BaseModel):
    included: bool


class GuideBrief(ORM):
    id: int
    target_language: str
    status: str
    created_at: UTCDateTime


class DocumentOut(ORM):
    id: int
    vendor_id: int
    vendor_name: str
    title: str | None
    source_type: str
    url: str | None
    page_count: int | None
    status: str
    error: str | None
    created_at: UTCDateTime


class DocumentDetail(DocumentOut):
    sections: list[SectionOut]
    guides: list[GuideBrief]


# ---- 요약 가이드 ----


class GuideCreate(BaseModel):
    target_language: str = Field(default="ko", min_length=2, max_length=20)


class SummaryOut(ORM):
    id: int
    version: int
    content: str
    key_steps: list[str]
    warnings: list[str]
    status: str
    error: str | None


class GuideItem(BaseModel):
    section_id: int
    title: str
    level: int
    page_start: int | None
    page_end: int | None
    summary: SummaryOut | None


class GuideProgress(BaseModel):
    total: int
    generated: int
    approved: int
    failed: int


class GuideDetail(BaseModel):
    id: int
    document_id: int
    document_title: str | None
    vendor_name: str
    target_language: str
    status: str
    overview: str | None
    progress: GuideProgress
    items: list[GuideItem]


class SummaryEdit(BaseModel):
    content: str


class RegenerateIn(BaseModel):
    comment: str = Field(min_length=1)


class RevisionOut(ORM):
    version: int
    content: str
    origin: str
    comment: str | None
    author_id: int | None
    created_at: UTCDateTime


# ---- 최종 문서 ----


class RevisionInfo(BaseModel):
    """문서 이력 관리 표에 들어가는 정보."""

    company: str | None = None
    department: str | None = None
    engineer: str | None = None
    phone: str | None = None
    email: str | None = None
    change_note: str | None = None


class ExportCreate(BaseModel):
    format: Literal["docx", "pptx"]
    doc_version: str = Field(default="1.0", min_length=1, max_length=50)
    include_logo: bool = False
    use_partner_template: bool = False
    revision: RevisionInfo | None = None


class ExportOut(ORM):
    id: int
    format: str
    doc_version: str
    include_logo: bool
    use_partner_template: bool
    revision: dict | None
    status: str
    error: str | None
    created_at: UTCDateTime


# ---- 2단계: 파트너 가이드 비교 ----


class PartnerGuideOut(ORM):
    id: int
    guide_id: int
    title: str | None
    source_type: str
    status: str
    error: str | None
    progress_current: int
    progress_total: int
    created_at: UTCDateTime


class PartnerSectionOut(BaseModel):
    id: int
    order_index: int
    level: int
    title: str
    page_start: int | None
    page_end: int | None
    char_count: int
    matched_section_id: int | None
    matched_title: str | None
    match_method: str | None


class VendorSectionOption(BaseModel):
    id: int
    title: str
    level: int


class FindingOut(BaseModel):
    id: int
    partner_section_id: int
    partner_section_title: str
    vendor_section_title: str | None
    vendor_page_start: int | None
    category: str
    severity: str
    before_text: str
    after_text: str
    reason: str
    evidence: str
    locatable: bool
    status: str
    final_text: str | None
    decision_note: str | None
    decided_by_name: str | None
    decided_at: UTCDateTime | None


class FindingCounts(BaseModel):
    total: int
    open: int
    accepted: int
    rejected: int


class PartnerGuideDetail(PartnerGuideOut):
    vendor_name: str
    vendor_document_title: str | None
    target_language: str
    sections: list[PartnerSectionOut]
    vendor_sections: list[VendorSectionOption]
    findings: list[FindingOut]
    counts: FindingCounts


class MatchPatch(BaseModel):
    matched_section_id: int | None


class DecisionIn(BaseModel):
    action: Literal["accept", "reject", "reopen"]
    final_text: str | None = None  # 수락 시 제안 문구 대신 반영할 문구
    note: str | None = None  # 판단 메모 (거절 시 필수)


class CorrectionLogOut(BaseModel):
    id: int
    finding_id: int
    action: str
    before_text: str
    after_text: str | None
    reason: str
    note: str | None
    user_name: str
    created_at: UTCDateTime


class CorrectionExportCreate(BaseModel):
    kind: Literal["tracked", "report"]


class CorrectionExportOut(ORM):
    id: int
    kind: str
    status: str
    applied_count: int
    skipped_count: int
    error: str | None
    created_at: UTCDateTime
