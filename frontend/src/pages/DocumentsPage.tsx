import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, download } from "../api";
import { useAuth } from "../auth";
import { DOC_TYPES, GUIDE_KINDS, STATUS_LABELS, type DocTypeKey, type GuideKindKey } from "../labels";
import type { DocumentSummary } from "../types";

const IN_PROGRESS = new Set(["uploaded", "parsing"]);

/** 벤더 문서: 규격서·기술 가이드·브로슈어 탭. 문서 가져오기는 하나로 두고 등록할 탭(종류)을 고른다. */
export default function DocumentsPage() {
  const { me } = useAuth();
  const [params, setParams] = useSearchParams();
  const docType = (DOC_TYPES.some((t) => t.key === params.get("type")) ? params.get("type") : "guide") as DocTypeKey;
  const listVendor = Number(params.get("vendor")) || "";
  const vendors = me?.vendors ?? [];
  const current = DOC_TYPES.find((t) => t.key === docType)!;

  // 탭·벤더를 바꿔도 다른 쪽 선택은 유지한다.
  const go = (next: { type?: DocTypeKey; vendor?: number | "" }) => {
    const type = next.type ?? docType;
    const vendor = next.vendor === undefined ? listVendor : next.vendor;
    setParams({ type, ...(vendor ? { vendor: String(vendor) } : {}) });
  };

  return (
    <>
      <div className="page-header">
        <h1>벤더 문서</h1>
        <p className="muted">벤더의 규격서·기술 가이드·브로슈어를 종류별로 등록하고 봅니다. 기술 가이드는 목차를 분석한 뒤 요약할 수 있습니다.</p>
      </div>

      <UploadForm defaultType={docType} onUploaded={(type) => type !== docType && go({ type })} />

      <div className="filters">
        {DOC_TYPES.map((t) => (
          <button key={t.key} className={t.key === docType ? "active" : ""} onClick={() => go({ type: t.key })}>
            {t.label}
          </button>
        ))}
      </div>

      <section className="card">
        <div className="summary-head">
          <h2 style={{ margin: 0 }}>{current.full}</h2>
        </div>
        <div className="form-row" style={{ margin: "8px 0 12px" }}>
          <label style={{ flex: "0 0 260px" }}>
            벤더
            <select value={listVendor} onChange={(e) => go({ vendor: Number(e.target.value) || "" })}>
              <option value="">전체 벤더</option>
              {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </label>
        </div>
        <DocumentTable
          query={`doc_type=${docType}${listVendor ? `&vendor_id=${listVendor}` : ""}`}
          showGuideKind={docType === "guide"}
        />
      </section>
    </>
  );
}

/** 문서 표 (문서 화면의 종류별 탭과 가이드 화면이 함께 쓴다). query 는 /documents 목록 API 의 검색 조건. */
export function DocumentTable({ query, showGuideKind = false }: { query: string; showGuideKind?: boolean }) {
  const { me } = useAuth();
  const isAdmin = me?.role === "platform_admin";
  const queryClient = useQueryClient();
  const [downloading, setDownloading] = useState<DocumentSummary | null>(null);
  const remove = useMutation({
    mutationFn: (id: number) => api(`/documents/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["documents"] }),
  });
  const docs = useQuery({
    queryKey: ["documents", query],
    queryFn: () => api<DocumentSummary[]>(`/documents?${query}`),
    refetchInterval: (q) => (q.state.data?.some((d) => IN_PROGRESS.has(d.status)) ? 2000 : false),
  });
  if (docs.isLoading) return <p className="muted">불러오는 중…</p>;
  if (docs.error) return <p className="error">{docs.error.message}</p>;
  if (!docs.data?.length) return <p className="muted">등록된 문서가 없습니다.</p>;
  return (
    <div className="table-wrap">
      {remove.error && <p className="error">{remove.error.message}</p>}
      {downloading && <DownloadDialog doc={downloading} onClose={() => setDownloading(null)} />}
      <table style={{ minWidth: 900 }}>
        <thead>
          <tr>
            <th>문서 이름</th>
            {showGuideKind && <th>가이드 종류</th>}
            <th>설명</th><th>벤더</th><th>등록자</th><th>등록 날짜</th><th>형식·분량</th><th>상태</th><th>다운로드</th>
            {isAdmin && <th>관리</th>}
          </tr>
        </thead>
        <tbody>
          {docs.data.map((d) => (
            <tr key={d.id}>
              <td><Link to={`/documents/${d.id}`}>{d.title ?? d.url ?? `문서 ${d.id}`}</Link></td>
              {showGuideKind && (
                <td style={{ whiteSpace: "nowrap" }}>{GUIDE_KINDS.find((k) => k.key === d.guide_kind)?.label ?? "-"}</td>
              )}
              <td style={{ maxWidth: 280 }}>{d.description ?? <span className="muted">-</span>}</td>
              <td>{d.vendor_name}</td>
              <td style={{ whiteSpace: "nowrap" }}>{d.uploaded_by_name ?? "-"}</td>
              <td style={{ whiteSpace: "nowrap" }}>{new Date(d.created_at).toLocaleDateString()}</td>
              <td style={{ whiteSpace: "nowrap" }}>{d.source_type.toUpperCase()}{d.page_count ? ` · ${d.page_count}쪽` : ""}</td>
              <td><span className={`badge ${d.status}`}>{STATUS_LABELS[d.status]}</span></td>
              <td>
                <button className="icon-button sm" title="다운로드" aria-label={`${d.title ?? "문서"} 다운로드`} onClick={() => setDownloading(d)}>
                  <DownloadIcon />
                </button>
              </td>
              {isAdmin && (
                <td>
                  <button
                    className="link danger-link"
                    disabled={remove.isPending}
                    onClick={() =>
                      window.confirm(`'${d.title ?? "문서"}' 문서를 삭제할까요?
목차, 요약 가이드, 생성한 문서 기록도 함께 지워지며 되돌릴 수 없습니다.`) &&
                      remove.mutate(d.id)
                    }
                  >
                    삭제
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DownloadIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3v12" />
      <path d="m7 10 5 5 5-5" />
      <path d="M5 21h14" />
    </svg>
  );
}

const FORMATS = [
  { key: "original", label: "원본 파일", hint: "올린 파일 그대로" },
  { key: "pptx", label: "PowerPoint", hint: ".pptx · 목차별 슬라이드" },
  { key: "docx", label: "Word", hint: ".docx · 목차별 본문" },
  { key: "xlsx", label: "Excel", hint: ".xlsx · 목차별 표" },
  { key: "pdf", label: "PDF", hint: ".pdf · 원본이 PDF 면 원본 그대로" },
] as const;

/** 다운로드 형식 고르기: 원본 또는 분석한 목차별 본문으로 만든 PPT·Word·Excel·PDF 를 내 PC 로 받는다. */
function DownloadDialog({ doc, onClose }: { doc: DocumentSummary; onClose: () => void }) {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function get(format: string) {
    setBusy(format);
    setError(null);
    try {
      await download(`/documents/${doc.id}/download?format=${format}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "내려받지 못했습니다.");
    } finally {
      setBusy(null);
    }
  }

  const parsed = doc.status === "parsed";
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="다운로드 형식 선택">
        <div className="summary-head">
          <h2 style={{ margin: 0 }}>다운로드</h2>
          <button className="link" onClick={onClose} aria-label="닫기">닫기</button>
        </div>
        <p className="muted">{doc.title ?? doc.url}</p>
        <div className="format-grid">
          {FORMATS.map((f) => {
            const unavailable = f.key === "original" ? doc.source_type === "url" : !parsed;
            return (
              <button key={f.key} className="format-option" disabled={!!busy || unavailable} onClick={() => get(f.key)}>
                <strong>{busy === f.key ? "만드는 중…" : f.label}</strong>
                <span className="muted">{unavailable ? (f.key === "original" ? "원본 파일 없음" : "분석 후 가능") : f.hint}</span>
              </button>
            );
          })}
        </div>
        <p className="muted" style={{ marginTop: 12, fontSize: "0.82rem" }}>
          PowerPoint·Word·Excel 은 분석한 목차별 본문으로 새로 만든 파일이라 원본의 그림·표 서식은 빠집니다.
        </p>
        {error && <p className="error">{error}</p>}
      </div>
    </div>
  );
}

function UploadForm({ defaultType, onUploaded }: { defaultType: DocTypeKey; onUploaded: (type: DocTypeKey) => void }) {
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const vendors = me?.vendors ?? [];
  const [chosenType, setDocType] = useState<DocTypeKey>();
  const docType = chosenType ?? defaultType; // 고르기 전에는 지금 보고 있는 탭
  const [guideKind, setGuideKind] = useState<GuideKindKey>("technical");
  const [vendorId, setVendorId] = useState<number | "">("");
  const [mode, setMode] = useState<"file" | "url">("file");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [inputKey, setInputKey] = useState(0);

  const upload = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("vendor_id", String(vendorId));
      form.append("doc_type", docType);
      if (docType === "guide") form.append("guide_kind", guideKind);
      if (title) form.append("title", title);
      if (description.trim()) form.append("description", description.trim());
      if (mode === "file" && file) form.append("file", file);
      if (mode === "url") form.append("url", url);
      return api<DocumentSummary>("/documents", { method: "POST", body: form });
    },
    onSuccess: (doc) => {
      setFile(null);
      setUrl("");
      setTitle("");
      setDescription("");
      setInputKey((k) => k + 1);
      setDocType(undefined);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      onUploaded(doc.doc_type);
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    upload.mutate();
  }

  return (
    <section className="card">
      <h2>문서 가져오기</h2>
      {vendors.length === 0 ? (
        <p className="muted">접근 가능한 벤더 도메인이 없습니다. 관리자에게 도메인 지정을 요청하세요.</p>
      ) : (
        <form className="form" onSubmit={submit}>
          <div className="form-row">
            <label style={{ flex: "0 0 200px" }}>
              등록할 탭 (문서 종류)
              <select value={docType} onChange={(e) => setDocType(e.target.value as DocTypeKey)}>
                {DOC_TYPES.map((t) => <option key={t.key} value={t.key}>{t.full}</option>)}
              </select>
            </label>
            {docType === "guide" && (
              <label style={{ flex: "0 0 180px" }}>
                가이드 종류
                <select value={guideKind} onChange={(e) => setGuideKind(e.target.value as GuideKindKey)}>
                  {GUIDE_KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
                </select>
              </label>
            )}
            <label>
              벤더 도메인
              <select value={vendorId} onChange={(e) => setVendorId(Number(e.target.value) || "")} required>
                <option value="">선택</option>
                {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
            </label>
            <label>
              제목 (선택)
              <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="비우면 문서 속 제목 또는 파일명 사용" />
            </label>
          </div>
          <label>
            설명 (선택)
            <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="예: 2026년 신제품 AER-600 규격, 영업 제안용" />
          </label>
          <div className="actions">
            <label className="check"><input type="radio" checked={mode === "file"} onChange={() => setMode("file")} />파일 (PDF, Word, PowerPoint)</label>
            <label className="check"><input type="radio" checked={mode === "url"} onChange={() => setMode("url")} />웹 문서 URL</label>
          </div>
          {mode === "file" ? (
            <input key={inputKey} type="file" accept=".pdf,.docx,.pptx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
          ) : (
            <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" required />
          )}
          {upload.error && <p className="error">{upload.error.message}</p>}
          <div><button className="primary" disabled={upload.isPending}>{upload.isPending ? "올리는 중…" : "올리기"}</button></div>
        </form>
      )}
    </section>
  );
}
