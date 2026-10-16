import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import { DOC_TYPES, GUIDE_KINDS, type DocTypeKey, type GuideKindKey } from "../labels";
import type { DocumentSummary } from "../types";
import { DocumentTable, uniqueOptions } from "./DocumentsPage";

type Filters = { vendor: number | ""; kind: GuideKindKey | ""; partner: number | ""; author: number | "" };

/** 등록한 가이드 (상단 '가이드' 기본 화면). */
export default function GuidesPage() {
  return <RegisteredTypePage docType="guide" />;
}

/** 등록한 규격서·가이드·브로슈어: 문서 등록에서 그 종류로 올린 문서. 벤더·(가이드 종류)·파트너·작성자로 거른다. */
export function RegisteredTypePage({ docType }: { docType: DocTypeKey }) {
  const { me } = useAuth();
  const [params, setParams] = useSearchParams();
  const label = DOC_TYPES.find((t) => t.key === docType)!.label;
  const isGuide = docType === "guide";
  const filters: Filters = {
    vendor: Number(params.get("vendor")) || "",
    kind: (isGuide && GUIDE_KINDS.some((k) => k.key === params.get("kind")) ? params.get("kind") : "") as GuideKindKey | "",
    partner: Number(params.get("partner")) || "",
    author: Number(params.get("author")) || "",
  };
  const vendors = me?.vendors ?? [];
  const kindLabel = GUIDE_KINDS.find((k) => k.key === filters.kind)?.label;

  // 파트너·작성자 선택지는 이 종류의 문서 전체에서 뽑는다 (표의 '전체' 조회와 같은 데이터라 한 번만 받는다).
  const all = useQuery({ queryKey: ["documents", `doc_type=${docType}`], queryFn: () => api<DocumentSummary[]>(`/documents?doc_type=${docType}`) });
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
    `doc_type=${docType}`,
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
        <h1>{label}</h1>
        <p className="muted">
          문서 등록에서 '{label}'(으)로 등록한 문서입니다. 새 문서는 <Link to={`/documents?type=${docType}`}>문서 등록</Link>에서 올리세요.
        </p>
      </div>
      {/* 선택칸 상자와 목록 상자를 나눠 둔다 */}
      <section className="card">
        <div className="form-row">
          <label style={{ flex: "0 0 200px" }}>
            벤더
            <select value={filters.vendor} onChange={(e) => go({ vendor: Number(e.target.value) || "" })}>
              <option value="">전체 벤더</option>
              {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </label>
          {isGuide && (
            <label style={{ flex: "0 0 200px" }}>
              가이드 종류
              <select value={filters.kind} onChange={(e) => go({ kind: e.target.value as GuideKindKey | "" })}>
                <option value="">전체 (기술 · 트러블 슈팅)</option>
                {GUIDE_KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
              </select>
            </label>
          )}
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
        <h2 className="section-title">{kindLabel ? `등록한 ${kindLabel}` : `등록한 ${label}`}</h2>
        {/* 종류를 고르면 그 종류만 보이므로 종류 열은 전체일 때만 보여 준다 */}
        <DocumentTable query={query} showGuideKind={isGuide && !filters.kind} />
      </section>
    </>
  );
}

/** 조직 요청 규격서·브로슈어: 같은 조직(회사) 사람들이 등록한 그 종류의 문서. 같은 조직이라 바로 내려받을 수 있다. */
export function OrgTypePage({ docType }: { docType: DocTypeKey }) {
  const { me } = useAuth();
  const [params, setParams] = useSearchParams();
  const label = DOC_TYPES.find((t) => t.key === docType)!.label;
  const vendor = Number(params.get("vendor")) || "";
  const vendors = me?.vendors ?? [];
  const query = [`doc_type=${docType}`, `partner_id=${me?.partner_id ?? 0}`, vendor && `vendor_id=${vendor}`].filter(Boolean).join("&");
  return (
    <>
      <div className="page-header">
        <h1>조직 요청 {label}</h1>
        <p className="muted">같은 조직({me?.partner_name ?? "소속 없음"}) 사람들이 등록한 {label}입니다. 같은 조직이면 바로 내려받을 수 있습니다.</p>
      </div>
      <section className="card">
        <div className="form-row">
          <label style={{ flex: "0 0 240px" }}>
            벤더
            <select value={vendor} onChange={(e) => setParams(Number(e.target.value) ? { vendor: e.target.value } : {})}>
              <option value="">전체 벤더</option>
              {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </label>
        </div>
      </section>
      <section className="card">
        <h2 className="section-title">조직 요청 {label}</h2>
        {me?.partner_id ? <DocumentTable query={query} showStatus={false} /> : <p className="muted">소속 조직이 지정되지 않았습니다.</p>}
      </section>
    </>
  );
}
