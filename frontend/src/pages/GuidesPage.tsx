import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import { DOC_TYPES, GUIDE_KINDS, type DocTypeKey, type GuideKindKey } from "../labels";
import ProductSelect from "../ProductSelect";
import type { DocumentSummary } from "../types";
import { DocumentTable, uniqueOptions } from "./DocumentsPage";

const FILTER_KEYS = ["vendor", "product", "detail", "kind", "partner", "author"] as const;
type FilterKey = (typeof FILTER_KEYS)[number];
type Filters = Record<FilterKey, string>;

/** 주소(?vendor=…&product=…)에 담긴 선택값을 읽고 바꾼다. 벤더를 바꾸면 제품군·상세는 풀린다. */
function useFilters(): [Filters, (next: Partial<Filters>) => void] {
  const [params, setParams] = useSearchParams();
  const filters = Object.fromEntries(FILTER_KEYS.map((k) => [k, params.get(k) ?? ""])) as Filters;
  const go = (next: Partial<Filters>) => {
    const merged = { ...filters, ...next };
    if (next.vendor !== undefined && next.vendor !== filters.vendor) {
      merged.product = "";
      merged.detail = "";
    }
    setParams(Object.fromEntries(Object.entries(merged).filter(([, v]) => v !== "")));
  };
  return [filters, go];
}

function buildQuery(base: string[], f: Filters): string {
  return [
    ...base,
    f.vendor && `vendor_id=${f.vendor}`,
    f.product && `product=${encodeURIComponent(f.product)}`,
    f.detail && `product_detail=${encodeURIComponent(f.detail)}`,
    f.kind && `guide_kind=${f.kind}`,
    f.partner && `partner_id=${f.partner}`,
    f.author && `uploaded_by=${f.author}`,
  ]
    .filter(Boolean)
    .join("&");
}

/** 벤더 → 제품군 → 상세 선택칸 */
function VendorProductFilters({ filters, go }: { filters: Filters; go: (next: Partial<Filters>) => void }) {
  const { me } = useAuth();
  const vendors = me?.vendors ?? [];
  return (
    <>
      <label style={{ flex: "0 0 200px" }}>
        벤더
        <select value={filters.vendor} onChange={(e) => go({ vendor: e.target.value })}>
          <option value="">전체 벤더</option>
          {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
        </select>
      </label>
      <ProductSelect
        filter
        vendorName={vendors.find((v) => String(v.id) === filters.vendor)?.name}
        product={filters.product}
        detail={filters.detail}
        onChange={(product, detail) => go({ product, detail })}
      />
    </>
  );
}

/** 등록한 가이드 (상단 '가이드' 기본 화면). */
export default function GuidesPage() {
  return <RegisteredTypePage docType="guide" />;
}

/** 등록한 규격서·가이드·브로슈어: 문서 등록에서 그 종류로 올린 문서. 벤더·제품군·상세·(가이드 종류)·파트너·작성자로 거른다. */
export function RegisteredTypePage({ docType }: { docType: DocTypeKey }) {
  const [filters, go] = useFilters();
  const label = DOC_TYPES.find((t) => t.key === docType)!.label;
  const isGuide = docType === "guide";
  const kindLabel = GUIDE_KINDS.find((k) => k.key === filters.kind)?.label;

  // 파트너·작성자 선택지는 이 종류의 문서 전체에서 뽑는다.
  const all = useQuery({ queryKey: ["documents", `doc_type=${docType}`], queryFn: () => api<DocumentSummary[]>(`/documents?doc_type=${docType}`) });
  const partners = uniqueOptions(all.data ?? [], (d) => (d.partner_id ? [d.partner_id, d.partner_name ?? `파트너 ${d.partner_id}`] : null));
  const authors = uniqueOptions(all.data ?? [], (d) => [d.uploaded_by, d.uploaded_by_name ?? `사용자 ${d.uploaded_by}`]);

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
          <VendorProductFilters filters={filters} go={go} />
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
            <select value={filters.partner} onChange={(e) => go({ partner: e.target.value })}>
              <option value="">전체 파트너</option>
              {partners.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </select>
          </label>
          <label style={{ flex: "0 0 200px" }}>
            작성자
            <select value={filters.author} onChange={(e) => go({ author: e.target.value })}>
              <option value="">전체 작성자</option>
              {authors.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </select>
          </label>
        </div>
      </section>
      <section className="card">
        <h2 className="section-title">{kindLabel ? `등록한 ${kindLabel}` : `등록한 ${label}`}</h2>
        {/* 종류를 고르면 그 종류만 보이므로 종류 열은 전체일 때만 보여 준다 */}
        <DocumentTable query={buildQuery([`doc_type=${docType}`], filters)} showGuideKind={isGuide && !filters.kind} />
      </section>
    </>
  );
}

/** 조직 요청 규격서·가이드·브로슈어: 같은 조직(회사) 사람들이 등록한 그 종류의 문서. 벤더·제품군·상세·사용자로 거른다. */
export function OrgTypePage({ docType }: { docType: DocTypeKey }) {
  const { me } = useAuth();
  const [filters, go] = useFilters();
  const label = DOC_TYPES.find((t) => t.key === docType)!.label;
  const orgBase = [`doc_type=${docType}`, `partner_id=${me?.partner_id ?? 0}`];
  // 사용자 선택지는 조직이 등록한 이 종류 문서에서 뽑는다.
  const all = useQuery({
    queryKey: ["documents", orgBase.join("&")],
    queryFn: () => api<DocumentSummary[]>(`/documents?${orgBase.join("&")}`),
    enabled: !!me?.partner_id,
  });
  const authors = uniqueOptions(all.data ?? [], (d) => [d.uploaded_by, d.uploaded_by_name ?? `사용자 ${d.uploaded_by}`]);
  return (
    <>
      <div className="page-header">
        <h1>조직 요청 {label}</h1>
        <p className="muted">같은 조직({me?.partner_name ?? "소속 없음"}) 사람들이 등록한 {label}입니다. 같은 조직이면 바로 내려받을 수 있습니다.</p>
      </div>
      <section className="card">
        <div className="form-row">
          <VendorProductFilters filters={filters} go={go} />
          <label style={{ flex: "0 0 200px" }}>
            사용자
            <select value={filters.author} onChange={(e) => go({ author: e.target.value })}>
              <option value="">전체 사용자</option>
              {authors.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
            </select>
          </label>
        </div>
      </section>
      <section className="card">
        <h2 className="section-title">조직 요청 {label}</h2>
        {me?.partner_id ? (
          <DocumentTable query={buildQuery(orgBase, filters)} showGuideKind={docType === "guide"} showStatus={false} />
        ) : (
          <p className="muted">소속 조직이 지정되지 않았습니다.</p>
        )}
      </section>
    </>
  );
}
