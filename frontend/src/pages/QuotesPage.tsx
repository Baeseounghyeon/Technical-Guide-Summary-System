import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, download, fetchBlob } from "../api";
import { useAuth } from "../auth";
import { QUOTE_CATEGORY_LABELS } from "../labels";
import type { Partner, QuoteFile } from "../types";

type Tab = "create" | "template" | "logo" | "files";
const TABS: [Tab, string][] = [
  ["create", "견적서 생성"],
  ["template", "견적서 양식"],
  ["logo", "로고"],
  ["files", "참고 자료"],
];

/** 영업: 견적서 생성과 그에 쓸 양식·로고·참고 자료 관리. */
export default function QuotesPage() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "create";
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
        <p className="muted">벤더 규격서·제품 기능 자료를 바탕으로 견적서를 만듭니다. 견적서 양식, 로고, 참고 자료를 먼저 등록해 두세요.</p>
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
          {tab === "template" && (
            <AssetTab
              partner={partner.data}
              kind="quote_template"
              title="견적서 양식"
              accept=".xlsx,.docx,.pptx,.pdf"
              hint="견적서를 만들 때 이 양식의 서식·항목 구성을 따릅니다. Excel(.xlsx), Word(.docx), PowerPoint(.pptx), PDF"
            />
          )}
          {tab === "logo" && (
            <AssetTab
              partner={partner.data}
              kind="quote_logo"
              title="견적서 로고"
              accept=".png,.jpg,.jpeg"
              hint="견적서 머리에 넣을 회사 로고입니다. PNG, JPG (엔지니어 문서용 로고와 따로 관리됩니다)"
            />
          )}
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
  const ready = [
    ["견적서 양식", !!partner.quote_template_path],
    ["로고", !!partner.quote_logo_path],
    ["참고 자료", (files.data?.length ?? 0) > 0],
  ] as const;
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

function AssetTab({
  partner, kind, title, accept, hint,
}: { partner: Partner; kind: "quote_template" | "quote_logo"; title: string; accept: string; hint: string }) {
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const ref = partner[`${kind}_path`];
  const canManage = me?.role === "platform_admin" || me?.role === "partner_admin";

  const upload = useMutation({
    mutationFn: (f: File) => {
      const form = new FormData();
      form.append("file", f);
      return api<Partner>(`/partners/${partner.id}/assets/${kind}`, { method: "POST", body: form });
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(["partner", partner.id], updated);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    },
  });

  return (
    <section className="card">
      <h2 className="section-title">{title}</h2>
      <p className="muted">{hint}</p>
      <p>
        현재: <span className={`badge ${ref ? "done" : ""}`}>{ref ? "등록됨" : "없음"}</span>{" "}
        {ref && kind === "quote_template" && (
          <button className="link" onClick={() => download(`/partners/${partner.id}/assets/${kind}`)}>내려받기</button>
        )}
      </p>
      {ref && kind === "quote_logo" && <AssetPreview partnerId={partner.id} kind={kind} refPath={ref} />}
      {canManage ? (
        <form
          className="form-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (file) upload.mutate(file);
          }}
        >
          <label>
            {ref ? "교체할 파일" : "등록할 파일"}
            <input ref={inputRef} type="file" accept={accept} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <button className="primary" disabled={!file || upload.isPending}>{upload.isPending ? "올리는 중…" : "업로드"}</button>
        </form>
      ) : (
        <p className="muted">양식·로고는 회사 관리자만 바꿀 수 있습니다.</p>
      )}
      {upload.error && <p className="error">{upload.error.message}</p>}
    </section>
  );
}

function AssetPreview({ partnerId, kind, refPath }: { partnerId: number; kind: string; refPath: string }) {
  const blob = useQuery({
    queryKey: ["partner", partnerId, kind, refPath],
    queryFn: () => fetchBlob(`/partners/${partnerId}/assets/${kind}`),
  });
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    if (!blob.data) return;
    const objectUrl = URL.createObjectURL(blob.data);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob.data]);
  return url ? <img src={url} alt="견적서 로고" style={{ maxHeight: 60, margin: "4px 0 12px" }} /> : null;
}

function FilesTab({ partnerId }: { partnerId: number }) {
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const key = ["quote-files", partnerId];
  const files = useQuery({ queryKey: key, queryFn: () => api<QuoteFile[]>(`/quote-files?partner_id=${partnerId}`) });
  const vendors = me?.vendors ?? [];
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [category, setCategory] = useState("spec");
  const [vendorId, setVendorId] = useState<number | "">("");
  const [note, setNote] = useState("");

  const upload = useMutation({
    mutationFn: (f: File) => {
      const form = new FormData();
      form.append("file", f);
      form.append("category", category);
      form.append("partner_id", String(partnerId));
      if (vendorId !== "") form.append("vendor_id", String(vendorId));
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
  const remove = useMutation({
    mutationFn: (id: number) => api(`/quote-files/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });

  return (
    <>
      <section className="card">
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
            <select value={vendorId} onChange={(e) => setVendorId(Number(e.target.value) || "")}>
              <option value="">(지정 안 함)</option>
              {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </label>
          <label>메모<input value={note} onChange={(e) => setNote(e.target.value)} placeholder="예: 2026년 상반기 가격표" /></label>
          <label>
            파일
            <input ref={inputRef} type="file" accept=".pdf,.docx,.xlsx,.pptx,.csv,.txt,.png,.jpg,.jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <button className="primary" disabled={!file || upload.isPending}>{upload.isPending ? "올리는 중…" : "올리기"}</button>
        </form>
        {upload.error && <p className="error">{upload.error.message}</p>}
      </section>

      <section className="card">
        <h2 className="section-title">등록된 참고 자료</h2>
        {remove.error && <p className="error">{remove.error.message}</p>}
        {files.data?.length === 0 && <p className="muted">아직 등록된 자료가 없습니다.</p>}
        {!!files.data?.length && (
          <div className="table-wrap">
            <table style={{ minWidth: 720 }}>
              <thead><tr><th>파일</th><th>종류</th><th>벤더</th><th>메모</th><th>등록일</th><th /></tr></thead>
              <tbody>
                {files.data.map((f) => (
                  <tr key={f.id}>
                    <td><button className="link" onClick={() => download(`/quote-files/${f.id}/download`)}>{f.filename}</button></td>
                    <td>{QUOTE_CATEGORY_LABELS[f.category]}</td>
                    <td>{f.vendor_name ?? <span className="muted">-</span>}</td>
                    <td>{f.note ?? <span className="muted">-</span>}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{new Date(f.created_at).toLocaleDateString()}</td>
                    <td>
                      <button
                        className="link danger-link"
                        disabled={remove.isPending}
                        onClick={() => window.confirm(`${f.filename} 을(를) 목록에서 삭제할까요?`) && remove.mutate(f.id)}
                      >
                        삭제
                      </button>
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
