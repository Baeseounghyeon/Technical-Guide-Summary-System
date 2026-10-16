export type Role = "platform_admin" | "partner_admin" | "engineer";
/** 업무 구분: 엔지니어(기술 가이드 요약) / 영업(견적서). null 이면 엔지니어 */
export type Track = "engineer" | "sales";

export interface Vendor {
  id: number;
  name: string;
  description: string | null;
}

export interface User {
  id: number;
  email: string;
  name: string;
  phone: string | null;
  department: string | null;
  company_name: string | null;
  role: Role;
  track: Track | null;
  status: "pending" | "active" | "suspended";
  partner_id: number | null;
  created_at: string;
}

export interface AdminUser extends User {
  partner_name: string | null;
  domains: string[];
  read_grants: { vendor_name: string; expires_at: string }[];
}

export interface Me extends User {
  partner_name: string | null;
  vendors: Vendor[];
}

export interface Partner {
  id: number;
  name: string;
  logo_path: string | null;
  docx_template_path: string | null;
  pptx_template_path: string | null;
  quote_template_path: string | null;
  quote_logo_path: string | null;
  vendors: Vendor[];
}

export interface GlossaryTerm {
  id: number;
  target_language: string;
  source_term: string;
  target_term: string;
}

export interface DocumentSummary {
  id: number;
  vendor_id: number;
  vendor_name: string;
  title: string | null;
  doc_type: "spec" | "guide" | "brochure";
  guide_kind: "technical" | "troubleshooting" | null;
  description: string | null;
  uploaded_by_name: string | null;
  source_type: "pdf" | "docx" | "pptx" | "url";
  url: string | null;
  page_count: number | null;
  status: "uploaded" | "parsing" | "parsed" | "failed";
  error: string | null;
  created_at: string;
}

export interface Section {
  id: number;
  parent_id: number | null;
  order_index: number;
  level: number;
  title: string;
  page_start: number | null;
  page_end: number | null;
  included: boolean;
  char_count: number;
}

export interface GuideBrief {
  id: number;
  target_language: string;
  status: GuideStatus;
  created_at: string;
}

export interface DocumentDetail extends DocumentSummary {
  sections: Section[];
  guides: GuideBrief[];
}

export type GuideStatus = "queued" | "summarizing" | "reviewing" | "approved";
export type SummaryStatus = "pending" | "generating" | "draft" | "approved" | "failed";

export interface Summary {
  id: number;
  version: number;
  content: string;
  key_steps: string[];
  warnings: string[];
  status: SummaryStatus;
  error: string | null;
}

export interface GuideItem {
  section_id: number;
  title: string;
  level: number;
  page_start: number | null;
  page_end: number | null;
  summary: Summary | null;
}

export interface GuideDetail {
  id: number;
  document_id: number;
  partner_id: number | null;
  document_title: string | null;
  vendor_name: string;
  target_language: string;
  status: GuideStatus;
  overview: string | null;
  progress: { total: number; generated: number; approved: number; failed: number };
  items: GuideItem[];
}

export interface Revision {
  version: number;
  content: string;
  origin: "generated" | "regenerated" | "edited";
  comment: string | null;
  author_id: number | null;
  created_at: string;
}

export interface RevisionInfo {
  company: string;
  department: string;
  engineer: string;
  phone: string;
  email: string;
  change_note: string;
}

export interface ExportItem {
  id: number;
  format: "docx" | "pptx";
  doc_version: string;
  include_logo: boolean;
  use_partner_template: boolean;
  revision: Partial<RevisionInfo> | null;
  status: "queued" | "done" | "failed";
  error: string | null;
  created_at: string;
}

// ---- 2단계: 파트너 가이드 비교 ----

export type PartnerGuideStatus = "uploaded" | "parsing" | "matched" | "comparing" | "reviewing" | "failed";
export type FindingStatus = "open" | "accepted" | "rejected";

export interface PartnerGuide {
  id: number;
  guide_id: number;
  title: string | null;
  source_type: "pdf" | "docx" | "pptx";
  status: PartnerGuideStatus;
  error: string | null;
  progress_current: number;
  progress_total: number;
  created_at: string;
}

export interface PartnerSection {
  id: number;
  order_index: number;
  level: number;
  title: string;
  page_start: number | null;
  page_end: number | null;
  char_count: number;
  matched_section_id: number | null;
  matched_title: string | null;
  match_method: "auto" | "manual" | null;
}

export interface Finding {
  id: number;
  partner_section_id: number;
  partner_section_title: string;
  vendor_section_title: string | null;
  vendor_page_start: number | null;
  category: string;
  severity: "high" | "medium" | "low";
  before_text: string;
  after_text: string;
  reason: string;
  evidence: string;
  locatable: boolean;
  status: FindingStatus;
  final_text: string | null;
  decision_note: string | null;
  decided_by_name: string | null;
  decided_at: string | null;
}

export interface PartnerGuideDetail extends PartnerGuide {
  vendor_name: string;
  vendor_document_title: string | null;
  target_language: string;
  sections: PartnerSection[];
  vendor_sections: { id: number; title: string; level: number }[];
  findings: Finding[];
  counts: { total: number; open: number; accepted: number; rejected: number };
}

export interface CorrectionLog {
  id: number;
  finding_id: number;
  action: "accepted" | "rejected" | "reopened";
  before_text: string;
  after_text: string | null;
  reason: string;
  note: string | null;
  user_name: string;
  created_at: string;
}

// ---- 파트너 간 가이드 공유 · 알림 ----

export interface SharedGuide {
  guide_id: number;
  title: string;
  vendor_name: string;
  owner_partner_name: string;
  target_language: string;
  formats: string[];
  updated_at: string;
  request_id: number | null;
  request_status: "none" | "pending" | "approved" | "rejected";
  decision_note: string | null;
}

export interface SharedExport {
  id: number;
  format: "docx" | "pptx";
  doc_version: string;
  created_at: string;
}

export interface DownloadRequest {
  id: number;
  guide_id: number;
  guide_title: string;
  vendor_name: string;
  requester_name: string;
  requester_email: string;
  requester_partner_name: string;
  owner_partner_name: string;
  message: string | null;
  status: "pending" | "approved" | "rejected";
  decided_by_name: string | null;
  decided_at: string | null;
  decision_note: string | null;
  created_at: string;
  can_decide: boolean;
}

export interface AppNotification {
  id: number;
  kind: "download_request" | "download_decision" | string;
  title: string;
  body: string | null;
  link: string | null;
  related_id: number | null;
  read_at: string | null;
  created_at: string;
  actionable: boolean;
}

// ---- 대시보드 ----

export type DocumentStage = "analyzing" | "not_started" | "summarizing" | "reviewing" | "approved" | "exported" | "failed";

export interface DashboardData {
  counts: { total: number; completed: number; in_progress: number; failed: number; exports: number; pending_reviews: number };
  documents: {
    id: number;
    title: string;
    vendor_name: string;
    source_type: string;
    page_count: number | null;
    created_at: string;
    stage: DocumentStage;
    guide_id: number | null;
    target_language: string | null;
    approved_sections: number;
    total_sections: number;
    exports: number;
  }[];
}

// ---- 3단계: 커뮤니티 ----

export type DomainAccess = "member" | "granted" | "none";

export interface Author {
  id: number;
  name: string;
  partner_name: string | null;
}

export interface Domain {
  vendor_id: number;
  vendor_name: string;
  access: DomainAccess;
  grant_expires_at: string | null;
  pending_request: boolean;
  post_count: number;
  upcoming_events: number;
}

export interface PostSummary {
  id: number;
  vendor_id: number;
  title: string;
  product: string | null;
  version: string | null;
  tags: string[];
  status: "open" | "resolved";
  author: Author;
  comment_count: number;
  created_at: string;
}

export interface PostComment {
  id: number;
  body: string;
  author: Author;
  created_at: string;
}

export interface PostDetail extends PostSummary {
  body: string;
  solution_comment_id: number | null;
  updated_at: string;
  comments: PostComment[];
  can_write: boolean;
  can_edit: boolean;
}

export interface SessionEvent {
  id: number;
  vendor_id: number;
  title: string;
  description: string;
  starts_at: string;
  ends_at: string | null;
  join_url: string | null;
  organizer: Author;
  attendee_count: number;
  attendees: string[];
  attending: boolean;
  can_edit: boolean;
}

export interface AccessGrant {
  id: number;
  user: Author;
  user_email: string;
  vendor_id: number;
  vendor_name: string;
  reason: string;
  requested_days: number;
  status: "pending" | "approved" | "rejected" | "revoked";
  grant_type: "read" | "member" | null;
  active: boolean;
  decided_by_name: string | null;
  decided_at: string | null;
  expires_at: string | null;
  decision_note: string | null;
  created_at: string;
}

export interface CorrectionExport {
  id: number;
  kind: "tracked" | "report";
  status: "queued" | "done" | "failed";
  applied_count: number;
  skipped_count: number;
  error: string | null;
  created_at: string;
}

export interface Usage {
  unlimited: boolean;
  quota_pages: number;
  used_pages: number;
  remaining_pages: number;
  regenerations_today: number;
  regeneration_limit: number;
  budget_exceeded: boolean;
  estimate_pages?: number;
}

export interface PartnerUsage {
  id: number;
  name: string;
  quota_pages: number;
  custom_quota: boolean;
  used_pages: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface UsageOverview {
  month: string;
  budget_usd: number;
  cost_usd: number;
  default_quota_pages: number;
  daily_regenerate_limit: number;
  chars_per_page: number;
  llm_provider: string;
  partners: PartnerUsage[];
  unassigned: { used_pages: number; cost_usd: number };
}

export interface QuoteFile {
  id: number;
  partner_id: number | null;
  vendor_id: number | null;
  vendor_name: string | null;
  category: "spec" | "feature" | "price" | "other";
  filename: string;
  note: string | null;
  uploaded_by: number;
  created_at: string;
}
