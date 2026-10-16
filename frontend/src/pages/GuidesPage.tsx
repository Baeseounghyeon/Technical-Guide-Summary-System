import { Link, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth";
import { GUIDE_KINDS, type GuideKindKey } from "../labels";
import { DocumentTable } from "./DocumentsPage";

/** 가이드: 문서 가져오기에서 '벤더 기술 가이드'로 등록한 문서. 벤더·가이드 종류로 걸러 본다. */
export default function GuidesPage() {
  const { me } = useAuth();
  const [params, setParams] = useSearchParams();
  const vendorId = Number(params.get("vendor")) || "";
  const kind = (GUIDE_KINDS.some((k) => k.key === params.get("kind")) ? params.get("kind") : "") as GuideKindKey | "";
  const vendors = me?.vendors ?? [];
  const kindLabel = GUIDE_KINDS.find((k) => k.key === kind)?.label;

  const go = (next: { vendor?: number | ""; kind?: GuideKindKey | "" }) => {
    const v = next.vendor === undefined ? vendorId : next.vendor;
    const k = next.kind === undefined ? kind : next.kind;
    setParams({ ...(v ? { vendor: String(v) } : {}), ...(k ? { kind: k } : {}) });
  };

  const query = ["doc_type=guide", vendorId && `vendor_id=${vendorId}`, kind && `guide_kind=${kind}`].filter(Boolean).join("&");

  return (
    <>
      <div className="page-header">
        <h1>가이드</h1>
        <p className="muted">
          문서 가져오기에서 '벤더 기술 가이드'로 등록한 문서입니다. 새 가이드는 <Link to="/documents?type=guide">문서</Link>에서 올리세요.
        </p>
      </div>
      <section className="card">
        <div className="form-row" style={{ marginBottom: 12 }}>
          <label style={{ flex: "0 0 260px" }}>
            벤더
            <select value={vendorId} onChange={(e) => go({ vendor: Number(e.target.value) || "" })}>
              <option value="">전체 벤더</option>
              {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </label>
          <label style={{ flex: "0 0 220px" }}>
            가이드 종류
            <select value={kind} onChange={(e) => go({ kind: e.target.value as GuideKindKey | "" })}>
              <option value="">전체 (기술 · 트러블 슈팅)</option>
              {GUIDE_KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
            </select>
          </label>
        </div>
        <h2 className="section-title">{kindLabel ? `등록된 ${kindLabel}` : "등록된 가이드"}</h2>
        {/* 종류를 고르면 그 종류만 보이므로 종류 열은 전체일 때만 보여 준다 */}
        <DocumentTable query={query} showGuideKind={!kind} />
      </section>
    </>
  );
}
