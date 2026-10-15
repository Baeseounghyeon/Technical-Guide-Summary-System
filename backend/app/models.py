from datetime import datetime, timezone
from enum import StrEnum

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(StrEnum):
    PLATFORM_ADMIN = "platform_admin"
    PARTNER_ADMIN = "partner_admin"
    ENGINEER = "engineer"


class UserStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class DocStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    FAILED = "failed"


class GuideStatus(StrEnum):
    QUEUED = "queued"
    SUMMARIZING = "summarizing"
    REVIEWING = "reviewing"
    APPROVED = "approved"


class SummaryStatus(StrEnum):
    PENDING = "pending"
    GENERATING = "generating"
    DRAFT = "draft"
    APPROVED = "approved"
    FAILED = "failed"


class ExportStatus(StrEnum):
    QUEUED = "queued"
    DONE = "done"
    FAILED = "failed"


class PartnerGuideStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    MATCHED = "matched"  # 목차 매칭 완료, 사용자가 확인 후 비교 시작
    COMPARING = "comparing"
    REVIEWING = "reviewing"
    FAILED = "failed"


class FindingStatus(StrEnum):
    OPEN = "open"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class JobKind(StrEnum):
    PARSE_DOCUMENT = "parse_document"
    SUMMARIZE_GUIDE = "summarize_guide"
    REGENERATE_SECTION = "regenerate_section"
    EXPORT_GUIDE = "export_guide"
    PARSE_PARTNER_GUIDE = "parse_partner_guide"
    COMPARE_PARTNER_GUIDE = "compare_partner_guide"
    EXPORT_CORRECTION = "export_correction"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


# 파트너사가 지원하는 벤더 도메인
partner_vendors = Table(
    "partner_vendors",
    Base.metadata,
    Column("partner_id", ForeignKey("partners.id", ondelete="CASCADE"), primary_key=True),
    Column("vendor_id", ForeignKey("vendors.id", ondelete="CASCADE"), primary_key=True),
)


class Vendor(Base):
    """벤더 = 도메인. 데이터 접근 경계의 기본 단위."""

    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Partner(Base):
    __tablename__ = "partners"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    logo_path: Mapped[str | None] = mapped_column(String(500))
    docx_template_path: Mapped[str | None] = mapped_column(String(500))
    pptx_template_path: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    vendors: Mapped[list[Vendor]] = relationship(secondary=partner_vendors)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(50))
    department: Mapped[str | None] = mapped_column(String(100))
    # 가입 신청 시 입력한 소속 회사명. 승인할 때 관리자가 partner_id 로 연결한다.
    company_name: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(30), default=Role.ENGINEER)
    status: Mapped[str] = mapped_column(String(20), default=UserStatus.PENDING)
    partner_id: Mapped[int | None] = mapped_column(ForeignKey("partners.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    partner: Mapped[Partner | None] = relationship()


class SourceDocument(Base):
    __tablename__ = "source_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    partner_id: Mapped[int | None] = mapped_column(ForeignKey("partners.id"), index=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str | None] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(String(10))  # pdf | docx | pptx | url
    file_path: Mapped[str | None] = mapped_column(String(500))
    url: Mapped[str | None] = mapped_column(String(2000))
    page_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=DocStatus.UPLOADED)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    vendor: Mapped[Vendor] = relationship()
    sections: Mapped[list["Section"]] = relationship(
        back_populates="document", order_by="Section.order_index", cascade="all, delete-orphan"
    )
    guides: Mapped[list["Guide"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Section(Base):
    """원본 문서의 목차 항목."""

    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"))
    order_index: Mapped[int] = mapped_column(Integer)
    level: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    # 목차 확인 단계에서 사용자가 요약 대상에서 뺄 수 있다.
    included: Mapped[bool] = mapped_column(Boolean, default=True)

    document: Mapped[SourceDocument] = relationship(back_populates="sections")
    parent: Mapped["Section | None"] = relationship(remote_side="Section.id")


class Guide(Base):
    """원본 문서 하나를 특정 언어로 요약한 가이드."""

    __tablename__ = "guides"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("source_documents.id", ondelete="CASCADE"), index=True)
    target_language: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default=GuideStatus.QUEUED)
    overview: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[SourceDocument] = relationship(back_populates="guides")
    summaries: Mapped[list["SectionSummary"]] = relationship(back_populates="guide", cascade="all, delete-orphan")
    exports: Mapped[list["Export"]] = relationship(
        back_populates="guide", order_by="Export.id", cascade="all, delete-orphan"
    )


class SectionSummary(Base):
    """목차 항목별 요약의 현재 상태. 과거 내용은 SummaryRevision 에 쌓인다."""

    __tablename__ = "section_summaries"
    __table_args__ = (UniqueConstraint("guide_id", "section_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    guide_id: Mapped[int] = mapped_column(ForeignKey("guides.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(Text, default="")
    key_steps: Mapped[list] = mapped_column(JSON, default=list)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default=SummaryStatus.PENDING)
    error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    guide: Mapped[Guide] = relationship(back_populates="summaries")
    section: Mapped[Section] = relationship()
    revisions: Mapped[list["SummaryRevision"]] = relationship(
        back_populates="summary", order_by="SummaryRevision.version", cascade="all, delete-orphan"
    )


class SummaryRevision(Base):
    __tablename__ = "summary_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    summary_id: Mapped[int] = mapped_column(ForeignKey("section_summaries.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    origin: Mapped[str] = mapped_column(String(20))  # generated | regenerated | edited
    comment: Mapped[str | None] = mapped_column(Text)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    summary: Mapped[SectionSummary] = relationship(back_populates="revisions")


class GlossaryTerm(Base):
    """벤더별 번역 용어집. 같은 벤더 문서끼리 번역 용어를 통일한다."""

    __tablename__ = "glossary_terms"
    __table_args__ = (UniqueConstraint("vendor_id", "target_language", "source_term"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), index=True)
    target_language: Mapped[str] = mapped_column(String(20))
    source_term: Mapped[str] = mapped_column(String(200))
    target_term: Mapped[str] = mapped_column(String(200))


class Export(Base):
    """최종 Word/PPT 생성 기록. revision 에 문서 이력 관리 정보를 담는다."""

    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(primary_key=True)
    guide_id: Mapped[int] = mapped_column(ForeignKey("guides.id", ondelete="CASCADE"), index=True)
    format: Mapped[str] = mapped_column(String(10))  # docx | pptx
    doc_version: Mapped[str] = mapped_column(String(50))
    include_logo: Mapped[bool] = mapped_column(Boolean, default=False)
    use_partner_template: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default=ExportStatus.QUEUED)
    file_path: Mapped[str | None] = mapped_column(String(500))
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    guide: Mapped[Guide] = relationship(back_populates="exports")


# ---------- 2단계: 파트너 가이드 비교와 오류 수정 ----------


class PartnerGuide(Base):
    """파트너사가 별도로 만든 기술 가이드. 승인된 요약 가이드(와 그 벤더 원본)를 기준으로 검토한다."""

    __tablename__ = "partner_guides"

    id: Mapped[int] = mapped_column(primary_key=True)
    guide_id: Mapped[int] = mapped_column(ForeignKey("guides.id", ondelete="CASCADE"), index=True)
    partner_id: Mapped[int | None] = mapped_column(ForeignKey("partners.id"), index=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str | None] = mapped_column(String(500))
    source_type: Mapped[str] = mapped_column(String(10))  # pdf | docx | pptx
    file_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default=PartnerGuideStatus.UPLOADED)
    error: Mapped[str | None] = mapped_column(Text)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    guide: Mapped[Guide] = relationship()
    sections: Mapped[list["PartnerSection"]] = relationship(
        back_populates="partner_guide", order_by="PartnerSection.order_index", cascade="all, delete-orphan"
    )
    findings: Mapped[list["Finding"]] = relationship(
        back_populates="partner_guide", order_by="Finding.id", cascade="all, delete-orphan"
    )
    exports: Mapped[list["CorrectionExport"]] = relationship(
        back_populates="partner_guide", order_by="CorrectionExport.id", cascade="all, delete-orphan"
    )


class PartnerSection(Base):
    """파트너 가이드의 목차 항목과, 대응하는 벤더 원본 목차 항목."""

    __tablename__ = "partner_sections"

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_guide_id: Mapped[int] = mapped_column(ForeignKey("partner_guides.id", ondelete="CASCADE"), index=True)
    order_index: Mapped[int] = mapped_column(Integer)
    level: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(500))
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, default="")
    matched_section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id", ondelete="SET NULL"))
    match_method: Mapped[str | None] = mapped_column(String(20))  # auto | manual

    partner_guide: Mapped[PartnerGuide] = relationship(back_populates="sections")
    matched_section: Mapped[Section | None] = relationship()


class Finding(Base):
    """오류 후보. 수정 전/후, 사유, 벤더 원본 근거를 가진다."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_guide_id: Mapped[int] = mapped_column(ForeignKey("partner_guides.id", ondelete="CASCADE"), index=True)
    partner_section_id: Mapped[int] = mapped_column(ForeignKey("partner_sections.id", ondelete="CASCADE"))
    vendor_section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.id", ondelete="SET NULL"))
    category: Mapped[str] = mapped_column(String(30))  # wrong_value | wrong_command | missing_step | ...
    severity: Mapped[str] = mapped_column(String(10))  # high | medium | low
    before_text: Mapped[str] = mapped_column(Text)
    after_text: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text, default="")
    # before_text 가 파트너 원문에 그대로 있어야 수정본에 자동 반영할 수 있다.
    locatable: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(20), default=FindingStatus.OPEN)
    final_text: Mapped[str | None] = mapped_column(Text)  # 수락 시 실제 반영할 문구 (사용자가 고칠 수 있음)
    decision_note: Mapped[str | None] = mapped_column(Text)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    partner_guide: Mapped[PartnerGuide] = relationship(back_populates="findings")
    partner_section: Mapped[PartnerSection] = relationship()
    vendor_section: Mapped[Section | None] = relationship()


class CorrectionLog(Base):
    """오류 수정 이력: 누가, 언제, 무엇을 어떻게 바꾸기로 했는지와 사유."""

    __tablename__ = "correction_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_guide_id: Mapped[int] = mapped_column(ForeignKey("partner_guides.id", ondelete="CASCADE"), index=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id", ondelete="CASCADE"))
    action: Mapped[str] = mapped_column(String(20))  # accepted | rejected | reopened
    before_text: Mapped[str] = mapped_column(Text)
    after_text: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CorrectionExport(Base):
    """수정 결과 파일. tracked: 변경 내용 추적 Word (Word 원본만), report: 수정 보고서 Word."""

    __tablename__ = "correction_exports"

    id: Mapped[int] = mapped_column(primary_key=True)
    partner_guide_id: Mapped[int] = mapped_column(ForeignKey("partner_guides.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))  # tracked | report
    status: Mapped[str] = mapped_column(String(20), default=ExportStatus.QUEUED)
    file_path: Mapped[str | None] = mapped_column(String(500))
    applied_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    partner_guide: Mapped[PartnerGuide] = relationship(back_populates="exports")


# ---------- 3단계: 벤더 도메인 커뮤니티 ----------


class PostStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class GrantStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"


class Post(Base):
    """이슈 처리 경험 공유 글. 벤더 도메인 단위로 모든 파트너사가 함께 본다."""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    product: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[str | None] = mapped_column(String(100))
    tags: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default=PostStatus.OPEN)
    solution_comment_id: Mapped[int | None] = mapped_column(Integer)  # 해결에 도움이 된 댓글
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    author: Mapped[User] = relationship()
    comments: Mapped[list["Comment"]] = relationship(
        back_populates="post", order_by="Comment.id", cascade="all, delete-orphan"
    )


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    post: Mapped[Post] = relationship(back_populates="comments")
    author: Mapped[User] = relationship()


class SessionEvent(Base):
    """온라인 세션 일정."""

    __tablename__ = "session_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), index=True)
    organizer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text, default="")
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    join_url: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    organizer: Mapped[User] = relationship()
    attendees: Mapped[list["EventAttendee"]] = relationship(cascade="all, delete-orphan")


class EventAttendee(Base):
    __tablename__ = "event_attendees"

    event_id: Mapped[int] = mapped_column(ForeignKey("session_events.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship()


class AccessGrant(Base):
    """다른 벤더 도메인 커뮤니티 열람 신청과 승인 기록. 승인되면 기간 동안 읽기만 가능."""

    __tablename__ = "access_grants"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(Text)
    requested_days: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(20), default=GrantStatus.PENDING)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    vendor: Mapped[Vendor] = relationship()


class Job(Base):
    """Worker 가 처리하는 백그라운드 작업 (DB 기반 큐)."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default=JobStatus.QUEUED, index=True)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
