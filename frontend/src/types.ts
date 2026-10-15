export type Role = "platform_admin" | "partner_admin" | "engineer";

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
  status: "pending" | "active" | "suspended";
  partner_id: number | null;
  created_at: string;
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
  vendors: Vendor[];
}

export interface DocumentSummary {
  id: number;
  vendor_id: number;
  vendor_name: string;
  title: string | null;
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
