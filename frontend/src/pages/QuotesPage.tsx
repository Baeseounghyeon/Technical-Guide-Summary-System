import { useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, download } from "../api";
import { useAuth } from "../auth";
import { QUOTE_CATEGORY_LABELS } from "../labels";
import ProductSelect, { productLabel } from "../ProductSelect";
import type { Partner, QuoteFile } from "../types";

type Tab = "create" | "files";
const TABS: [Tab, string][] = [
  ["create", "견적서 생성"],
  ["files", "참고 자료"],
];

/** 영업: 견적서 참고 자료 관리. (견적서 양식은 '견적서 생성 > 가져오기 > 견적서 양식'에서, 로고는 양식 엑셀 안에) */
export default function QuotesPage() {
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get("tab") === "files" ? "files" : "create";
  const { me } = useAuth();
  const isPlatformAdmin = me?.role === "platform_admin";
  // 플랫폼 관리자는 회사를 골라서, 영업 사용자는 자기 회사 것만 다룬다.
  const partners = useQuery({
    queryKey: ["admin", "partners"],
    queryFn: () => api<Partner[]>("/admin/partners"),
    enabled: isPlatformAdmin,
  });
  const [chosen, setChosen] = useState<number>();
  const partnerId = isPlatformAdmin ? (chosen ?? me?.partner_id ?? partners.data?.[0]?.id) : me?.partner_id;
  const partner = useQuery({
    queryKey: ["partner", partnerId],
    queryFn: () => api<Partner>(`/partners/${partnerId}`),
    enabled: partnerId != null,
  });

  return (
    <>
      <div className="page-header">
        <h1>견적서</h1>
        <p className="muted">벤더 규격서·제품 기능 자료를 바탕으로 견적서를 만듭니다. 견적서 양식은 견적서 생성 화면에서 올리고, 참고 자료는 여기서 등록해 두세요.</p>
      </div>
      {isPlatformAdmin && (
        <div className="form-row" style={{ marginBottom: 12 }}>
          <label style={{ flex: "0 0 280px" }}>
            회사
            <select value={partnerId ?? ""} onChange={(e) => setChosen(Number(e.target.value))}>
              {partners.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
        </div>
      )}
      {partnerId == null && <p className="error">소속 회사가 지정되지 않았습니다. 관리자에게 문의하세요.</p>}
      <div className="filters">
        {TABS.map(([key, label]) => (
          <button key={key} className={tab === key ? "active" : ""} onClick={() => setParams(key === "create" ? {} : { tab: key })}>
            {label}
          </button>
        ))}
      </div>
      {partner.error && <p className="error">{partner.error.message}</p>}
      {partner.data && (
        <>
          {tab === "create" && <CreateTab partner={partner.data} />}
          {tab === "files" && <FilesTab partnerId={partner.data.id} />}
        </>
      )}
    </>
  );
}

function CreateTab({ partner }: { partner: Partner }) {
  const files = useQuery({
    queryKey: ["quote-files", partner.id],
    queryFn: () => api<QuoteFile[]>(`/quote-files?partner_id=${partner.id}`),
  });
  const ready = [["참고 자료", (files.data?.length ?? 0) > 0]] as const;
  return (
    <section className="card">
      <h2 className="section-title">견적서 생성</h2>
      <p className="muted">
        요청하는 벤더의 규격서·제품 기능 자료와 등록한 양식을 바탕으로 견적서를 만드는 기능입니다. 세부 생성 방식은 준비 중이며, 지금은 필요한 자료를
        미리 등록해 둘 수 있습니다.
      </p>
      <ul>
        {ready.map(([label, ok]) => (
          <li key={label}>
            {label}: <span className={`badge ${ok ? "done" : ""}`}>{ok ? "등록됨" : "없음"}</span>
            {label === "참고 자료" && ok && <span className="muted"> {files.data?.length}개</span>}
          </li>
        ))}
      </ul>
      <button className="primary" disabled>견적서 생성 (준비 중)</button>
    </section>
  );
}

function FilesTab({ partnerId }: { partnerId: number }) {
  const { me } = useAuth();
  // 엔지니어 등 견적서 권한이 없으면 내려받기만
  const canEdit = me?.role === "platform_admin" || !!me?.permissions.includes("quote");
  const queryClient = useQueryClient();
  const key = ["quote-files", partnerId];
  const files = useQuery({ queryKey: key, queryFn: () => api<QuoteFile[]>(`/quote-files?partner_id=${partnerId}`) });
  const vendors = me?.vendors ?? [];
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState("spec");
  const [vendorId, setVendorId] = useState<number | "">("");
  const [product, setProduct] = useState({ product: "", detail: "" });
  // 목록 거르기: 벤더 → 제품군 → 상세
  const [view, setView] = useState({ vendor: "", product: "", detail: "" });
  const [note, setNote] = useState("");

  const upload = useMutation({
    mutationFn: (f: File) => {
      const form = new FormData();
      form.append("file", f);
      form.append("category", category);
      form.append("partner_id", String(partnerId));
      if (vendorId !== "") form.append("vendor_id", String(vendorId));
      if (product.product) form.append("product", product.product);
      if (product.detail) form.append("product_detail", product.detail);
      if (note.trim()) form.append("note", note.trim());
      return api<QuoteFile>("/quote-files", { method: "POST", body: form });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: key });
      setFile(null);
      setNote("");
      if (inputRef.current) inputRef.current.value = "";
    },
  });
  const shown = (files.data ?? []).filter(
    (f) =>
      (!view.vendor || String(f.vendor_id) === view.vendor) &&
      (!view.product || f.product === view.product) &&
      (!view.detail || f.product_detail === view.detail),
  );
  const remove = useMutation({
    mutationFn: (id: number) => api(`/quote-files/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });

  return (
    <>
      {canEdit && <section className="card">
        <h2 className="section-title">참고 자료 올리기</h2>
        <p className="muted">벤더 규격서, 제품 기능 소개, 가격표 등 견적서를 만들 때 참고할 파일입니다. 같은 회사의 영업 담당자가 함께 씁니다.</p>
        <form
          className="form-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (file) upload.mutate(file);
          }}
        >
          <label style={{ flex: "0 0 140px" }}>
            종류
            <select value={category} onChange={(e) => setCategory(e.target.value)}>
              {Object.entries(QUOTE_CATEGORY_LABELS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label style={{ flex: "0 0 200px" }}>
            벤더
            <select
              value={vendorId}
              onChange={(e) => {
                setVendorId(Number(e.target.value) || "");
                setProduct({ product: "", detail: "" });
              }}
            >
              <option value="">(지정 안 함)</option>
              {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </label>
          <ProductSelect
            vendorName={vendors.find((v) => v.id === vendorId)?.name}
            product={product.product}
            detail={product.detail}
            onChange={(p, d) => setProduct({ product: p, detail: d })}
          />
          <label>메모<input value={note} onChange={(e) => setNote(e.target.value)} placeholder="예: 2026년 상반기 가격표" /></label>
          <label>
            파일
            <input ref={inputRef} type="file" accept=".pdf,.docx,.xlsx,.pptx,.csv,.txt,.png,.jpg,.jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <button className="primary" disabled={!file || upload.isPending}>{upload.isPending ? "올리는 중…" : "올리기"}</button>
        </form>
        {upload.error && <p className="error">{upload.error.message}</p>}
      </section>}

      <section className="card">
        <h2 className="section-title">등록된 참고 자료</h2>
        <div className="form-row" style={{ marginBottom: 12 }}>
          <label style={{ flex: "0 0 200px" }}>
            벤더
            <select value={view.vendor} onChange={(e) => setView({ vendor: e.target.value, product: "", detail: "" })}>
              <option value="">전체 벤더</option>
              {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </label>
          <ProductSelect
            filter
            vendorName={vendors.find((v) => String(v.id) === view.vendor)?.name}
            product={view.product}
            detail={view.detail}
            onChange={(p, d) => setView((x) => ({ ...x, product: p, detail: d }))}
          />
        </div>
        {remove.error && <p className="error">{remove.error.message}</p>}
        {files.data?.length === 0 && <p className="muted">아직 등록된 자료가 없습니다.</p>}
        {!!files.data?.length && shown.length === 0 && <p className="muted">선택한 조건에 맞는 자료가 없습니다.</p>}
        {shown.length > 0 && (
          <div className="table-wrap">
            <table style={{ minWidth: 720 }}>
              <thead><tr><th>파일</th><th>종류</th><th>벤더</th><th>제품</th><th>메모</th><th>등록일</th><th /></tr></thead>
              <tbody>
                {shown.map((f) => (
                  <tr key={f.id}>
                    <td><button className="link" onClick={() => download(`/quote-files/${f.id}/download`)}>{f.filename}</button></td>
                    <td>{QUOTE_CATEGORY_LABELS[f.category]}</td>
                    <td>{f.vendor_name ?? <span className="muted">-</span>}</td>
                    <td>{productLabel(f.product, f.product_detail)}</td>
                    <td>{f.note ?? <span className="muted">-</span>}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{new Date(f.created_at).toLocaleDateString()}</td>
                    <td>
                      {canEdit && <button
                        className="link danger-link"
                        disabled={remove.isPending}
                        onClick={() => window.confirm(`${f.filename} 을(를) 목록에서 삭제할까요?`) && remove.mutate(f.id)}
                      >
                        삭제
                      </button>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
