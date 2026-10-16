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
    track: Literal["engineer", "sales"] = "engineer"


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
    track: str | None
    status: str
    partner_id: int | None
    created_at: UTCDateTime


class MeOut(UserOut):
    partner_name: str | None
    vendors: list[VendorOut]


class ReadGrantBrief(BaseModel):
    vendor_name: str
    expires_at: UTCDateTime


class AdminUserOut(UserOut):
    """관리자 가입자 목록용: 소속, 할당된 도메인, 열람 권한까지."""

    partner_name: str | None
    domains: list[str]  # 소속 파트너사의 정식 도메인 (플랫폼 관리자는 전체)
    read_grants: list[ReadGrantBrief]  # 기간 한정 읽기 전용 열람 (유효한 것만)


class ApproveIn(BaseModel):
    partner_id: int | None = None
    role: Literal["platform_admin", "partner_admin", "engineer"] = "engineer"
    track: Literal["engineer", "sales"] | None = None  # 비우면 그대로 둔다


# ---- 파트너 / 벤더 ----


class PartnerIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class PartnerOut(ORM):
    id: int
    name: str
    logo_path: str | None
    docx_template_path: str | None
    pptx_template_path: str | None
    quote_template_path: str | None
    quote_logo_path: str | None
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
    partner_id: int | None  # 원본 문서를 올린 파트너사
    document_title: str | None
    vendor_name: str
    target_language: str
    status: str
    overview: str | None
    progress: GuideProgress
    items: list[GuideItem]


class BulkApproveOut(BaseModel):
    approved: int  # 이번에 승인한 항목 수
    remaining: int  # 아직 승인되지 않은 항목 수 (생성 중·실패 등)
    guide_status: str


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
    # 로고·양식을 가져올 파트너사. 비우면 원본 문서의 파트너사. 관리자는 아무 파트너사나 고를 수 있다.
    partner_id: int | None = None
    doc_version: str = Field(default="1.0", min_length=1, max_length=50)
    include_logo: bool = False
    use_partner_template: bool = False
    revision: RevisionInfo | None = None


class ExportOut(ORM):
    id: int
    partner_id: int | None
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


# ---- 파트너 간 가이드 공유 · 알림 ----


class SharedGuideOut(BaseModel):
    guide_id: int
    title: str
    vendor_name: str
    owner_partner_name: str
    target_language: str
    formats: list[str]  # 만들어진 최종 문서 형식 (docx, pptx)
    updated_at: UTCDateTime  # 가장 최근 최종 문서 생성 시각
    request_id: int | None
    request_status: Literal["none", "pending", "approved", "rejected"]
    decision_note: str | None


class SharedExportOut(BaseModel):
    id: int
    format: str
    doc_version: str
    created_at: UTCDateTime


class DownloadRequestIn(BaseModel):
    message: str | None = Field(default=None, max_length=1000)


class DownloadRequestOut(BaseModel):
    id: int
    guide_id: int
    guide_title: str
    vendor_name: str
    requester_name: str
    requester_email: str
    requester_partner_name: str
    owner_partner_name: str
    message: str | None
    status: str
    decided_by_name: str | None
    decided_at: UTCDateTime | None
    decision_note: str | None
    created_at: UTCDateTime
    can_decide: bool


class DownloadDecisionIn(BaseModel):
    approve: bool
    note: str | None = None


class NotificationOut(ORM):
    id: int
    kind: str
    title: str
    body: str | None
    link: str | None
    related_id: int | None
    read_at: UTCDateTime | None
    created_at: UTCDateTime
    # download_request 알림일 때 요청이 아직 대기 중이면 알림 안에서 바로 승인/거절할 수 있다.
    actionable: bool = False


class NotificationList(BaseModel):
    unread: int
    items: list[NotificationOut]


# ---- 대시보드 ----


class DashboardCounts(BaseModel):
    total: int  # 내가 올린 문서
    completed: int  # 요약 승인 완료 (최종 문서 생성 여부 무관)
    in_progress: int  # 분석 중 · 요약 전 · 요약 중 · 검토 중
    failed: int
    exports: int  # 만든 최종 문서(Word/PPT) 수
    pending_reviews: int  # 검토 중 문서에서 아직 승인하지 않은 요약 항목 수


class DashboardDocument(BaseModel):
    id: int
    title: str
    vendor_name: str
    source_type: str
    page_count: int | None
    created_at: UTCDateTime
    stage: Literal["analyzing", "not_started", "summarizing", "reviewing", "approved", "exported", "failed"]
    guide_id: int | None
    target_language: str | None
    approved_sections: int
    total_sections: int
    exports: int


class DashboardOut(BaseModel):
    counts: DashboardCounts
    documents: list[DashboardDocument]


# ---- 3단계: 커뮤니티 ----


class Author(BaseModel):
    id: int
    name: str
    partner_name: str | None


class DomainOut(BaseModel):
    vendor_id: int
    vendor_name: str
    access: Literal["member", "granted", "none"]
    grant_expires_at: UTCDateTime | None = None
    pending_request: bool = False
    post_count: int = 0
    upcoming_events: int = 0


class PostIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    product: str | None = Field(default=None, max_length=200)
    version: str | None = Field(default=None, max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=10)


class PostSummary(BaseModel):
    id: int
    vendor_id: int
    title: str
    product: str | None
    version: str | None
    tags: list[str]
    status: str
    author: Author
    comment_count: int
    created_at: UTCDateTime


class CommentOut(BaseModel):
    id: int
    body: str
    author: Author
    created_at: UTCDateTime


class PostDetail(PostSummary):
    body: str
    solution_comment_id: int | None
    updated_at: UTCDateTime
    comments: list[CommentOut]
    can_write: bool  # 열람 승인(읽기 전용) 사용자는 false
    can_edit: bool  # 작성자 또는 관리자


class CommentIn(BaseModel):
    body: str = Field(min_length=1)


class PostStatusIn(BaseModel):
    status: Literal["open", "resolved"]
    solution_comment_id: int | None = None


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = ""
    starts_at: datetime
    ends_at: datetime | None = None
    join_url: str | None = Field(default=None, max_length=1000)


class EventOut(BaseModel):
    id: int
    vendor_id: int
    title: str
    description: str
    starts_at: UTCDateTime
    ends_at: UTCDateTime | None
    join_url: str | None
    organizer: Author
    attendee_count: int
    attendees: list[str]
    attending: bool
    can_edit: bool


class AccessRequestIn(BaseModel):
    reason: str = Field(min_length=1)
    days: int = Field(default=30, ge=1, le=365)


class AccessGrantOut(BaseModel):
    id: int
    user: Author
    user_email: str
    vendor_id: int
    vendor_name: str
    reason: str
    requested_days: int
    status: str
    grant_type: str | None
    active: bool
    decided_by_name: str | None
    decided_at: UTCDateTime | None
    expires_at: UTCDateTime | None
    decision_note: str | None
    created_at: UTCDateTime


class AccessDecisionIn(BaseModel):
    approve: bool
    # read: 기간 한정 읽기 전용 / member: 신청자의 파트너사에 도메인 정식 부여(읽기·쓰기·문서 업로드)
    grant_type: Literal["read", "member"] = "read"
    days: int | None = Field(default=None, ge=1, le=365)  # read 일 때만. 비우면 신청 기간
    note: str | None = None


class QuoteFileOut(ORM):
    id: int
    partner_id: int | None
    vendor_id: int | None
    vendor_name: str | None = None
    category: str
    filename: str
    note: str | None
    uploaded_by: int
    created_at: UTCDateTime
