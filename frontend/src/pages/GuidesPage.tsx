import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import { GUIDE_KINDS, type GuideKindKey } from "../labels";
import type { DocumentSummary } from "../types";
import { DocumentTable, uniqueOptions } from "./DocumentsPage";

type Filters = { vendor: number | ""; kind: GuideKindKey | ""; partner: number | ""; author: number | "" };

/** 가이드: 문서 가져오기에서 '벤더 기술 가이드'로 등록한 문서. 벤더·가이드 종류·파트너·작성자로 걸러 본다. */
export default function GuidesPage() {
  const { me } = useAuth();
  const [params, setParams] = useSearchParams();
  const filters: Filters = {
    vendor: Number(params.get("vendor")) || "",
    kind: (GUIDE_KINDS.some((k) => k.key === params.get("kind")) ? params.get("kind") : "") as GuideKindKey | "",
    partner: Number(params.get("partner")) || "",
    author: Number(params.get("author")) || "",
  };
  const vendors = me?.vendors ?? [];
  const kindLabel = GUIDE_KINDS.find((k) => k.key === filters.kind)?.label;

  // 파트너·작성자 선택지는 등록된 가이드 전체에서 뽑는다 (표의 '전체' 조회와 같은 데이터라 한 번만 받는다).
  const all = useQuery({ queryKey: ["documents", "doc_type=guide"], queryFn: () => api<DocumentSummary[]>("/documents?doc_type=guide") });
  const partners = uniqueOptions(all.data ?? [], (d) => (d.partner_id ? [d.partner_id, d.partner_name ?? `파트너 ${d.partner_id}`] : null));
  const authors = uniqueOptions(all.data ?? [], (d) => [d.uploaded_by, d.uploaded_by_name ?? `사용자 ${d.uploaded_by}`]);

  const go = (next: Partial<Filters>) => {
    const f = { ...filters, ...next };
    setParams(
      Object.fromEntries(
        Object.entries({ vendor: f.vendor, kind: f.kind, partner: f.partner, author: f.author })
          .filter(([, v]) => v !== "")
          .map(([k, v]) => [k, String(v)]),
      ),
    );
  };

  const query = [
    "doc_type=guide",
    filters.vendor && `vendor_id=${filters.vendor}`,
    filters.kind && `guide_kind=${filters.kind}`,
    filters.partner && `partner_id=${filters.partner}`,
    filters.author && `uploaded_by=${filters.author}`,
  ]
    .filter(Boolean)
    .join("&");

  return (
    <>
      <div className="page-header">
        <h1>가이드</h1>
        <p className="muted">
          문서 가져오기에서 '벤더 기술 가이드'로 등록한 문서입니다. 새 가이드는 <Link to="/documents">문서 등록</Link>에서 올리세요.
        </p>
      </div>
      {/* 선택칸 상자와 가이드 목록 상자를 나눠 둔다 */}
      <section className="card">
        <div className="form-row">
          <label style={{ flex: "0 0 200px" }}>
            벤더
            <select value={filters.vendor} onChange={(e) => go({ vendor: Number(e.target.value) || "" })}>
              <option value="">전체 벤더</option>
              {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </label>
          <label style={{ flex: "0 0 200px" }}>
            가이드 종류
            <select value={filters.kind} onChange={(e) => go({ kind: e.target.value as GuideKindKey | "" })}>
              <option value="">전체 (기술 · 트러블 슈팅)</option>
              {GUIDE_KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
            </select>
          </label>
          <label style={{ flex: "0 0 200px" }}>
            파트너
            <select value={filters.partner} onChange={(e) => go({ partner: Number(e.target.value) || "" })}>
              <option value="">전체 파트너</option>
              {partners.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </select>
          </label>
          <label style={{ flex: "0 0 200px" }}>
            작성자
            <select value={filters.author} onChange={(e) => go({ author: Number(e.target.value) || "" })}>
              <option value="">전체 작성자</option>
              {authors.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </select>
          </label>
        </div>
      </section>
      <section className="card">
        <h2 className="section-title">{kindLabel ? `등록한 ${kindLabel}` : "등록한 가이드"}</h2>
        {/* 종류를 고르면 그 종류만 보이므로 종류 열은 전체일 때만 보여 준다 */}
        <DocumentTable query={query} showGuideKind={!filters.kind} />
      </section>
    </>
  );
}
