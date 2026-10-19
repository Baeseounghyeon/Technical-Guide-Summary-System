import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, download } from "../api";
import { useAuth } from "../auth";
import { DOC_TYPES, docTypeLabel, GUIDE_KINDS, STATUS_LABELS, type DocTypeKey, type GuideKindKey } from "../labels";
import ProductSelect, { productLabel } from "../ProductSelect";
import type { DocumentSummary } from "../types";

const IN_PROGRESS = new Set(["uploaded", "parsing"]);

/** 문서 등록: 문서 가져오기 양식만 보여 준다. 올린 뒤에는 '등록한 문서'의 해당 종류 탭으로 간다.
 *  ?type=spec|guide|brochure 로 오면 등록할 종류를 미리 골라 둔다 (가이드 생성·가이드 공유 화면의 문서 등록 링크 등). */
export default function DocumentsPage() {
  const navigate = useNavigate();
  const { me } = useAuth();
  const [params] = useSearchParams();
  // 등록할 수 있는 종류만 (엔지니어: 가이드·브로슈어 / 영업: 규격서·브로슈어 / 관리자: 전부 + 승인된 추가 권한)
  const allowed = DOC_TYPES.filter((t) => me?.role === "platform_admin" || me?.permissions.includes(t.key)).map((t) => t.key);
  const wanted = params.get("type") as DocTypeKey | null;
  const preset = (wanted && allowed.includes(wanted) ? wanted : allowed[0] ?? "brochure") as DocTypeKey;
  return (
    <>
      <div className="page-header">
        <h1>문서 등록</h1>
        <p className="muted">
          벤더의 규격서·기술 가이드·견적서·제품 가격표·매입 금액·브로슈어를 등록합니다. 기술 가이드는 목차를 분석한 뒤 요약할 수 있습니다. 올린 문서는{" "}
          <Link to="/documents/registered">등록한 문서</Link>에서 봅니다.
        </p>
      </div>
      <UploadForm key={preset} defaultType={preset} allowed={allowed} onUploaded={(type) => navigate(`/documents/registered?type=${type}`)} />
    </>
  );
}

/** 등록한 문서: 규격서·기술 가이드·브로슈어 탭, 벤더·등록자로 거른다. */
export function RegisteredDocumentsPage() {
  const { me } = useAuth();
  const [params, setParams] = useSearchParams();
  const docType = (DOC_TYPES.some((t) => t.key === params.get("type")) ? params.get("type") : "spec") as DocTypeKey;
  const listVendor = Number(params.get("vendor")) || "";
  const author = Number(params.get("author")) || "";
  const vendors = me?.vendors ?? [];
  const current = DOC_TYPES.find((t) => t.key === docType)!;

  // 등록자 선택지는 지금 탭(종류)의 문서 전체에서 뽑는다.
  const all = useQuery({ queryKey: ["documents", `doc_type=${docType}`], queryFn: () => api<DocumentSummary[]>(`/documents?doc_type=${docType}`) });
  const authors = uniqueOptions(all.data ?? [], (d) => [d.uploaded_by, d.uploaded_by_name ?? `사용자 ${d.uploaded_by}`]);

  // 탭을 바꾸면 등록자 선택은 풀고(종류마다 등록자가 다름), 벤더 선택은 유지한다.
  const go = (next: { type?: DocTypeKey; vendor?: number | ""; author?: number | "" }) => {
    const type = next.type ?? docType;
    const vendor = next.vendor === undefined ? listVendor : next.vendor;
    const who = next.type ? "" : next.author === undefined ? author : next.author;
    setParams({ type, ...(vendor ? { vendor: String(vendor) } : {}), ...(who ? { author: String(who) } : {}) });
  };
  // 등록한 문서는 본인이 올린 것만 (다른 사람 문서는 규격서·가이드·브로슈어 메뉴에서). 관리자는 전체.
  const isAdmin = me?.role === "platform_admin";
  const who = isAdmin ? author : me?.id ?? 0;
  const query = [`doc_type=${docType}`, listVendor && `vendor_id=${listVendor}`, who && `uploaded_by=${who}`].filter(Boolean).join("&");

  return (
    <>
      <div className="page-header">
        <h1>등록한 문서</h1>
        <p className="muted">
          내가 문서 등록에서 올린 문서를 종류별로 봅니다(규격서·가이드·견적서·제품 가격표·매입 금액·브로슈어). 다른 사람이 올린 문서는 상단의 규격서·가이드·견적서·브로슈어 메뉴에서 확인하세요.
          새 문서는 <Link to="/documents">문서 등록</Link>에서 올리세요.
        </p>
      </div>

      <div className="filters">
        {DOC_TYPES.filter((t) => !SALES_ONLY_TYPES.includes(t.key) || isAdmin || me?.permissions.includes(t.key)).map((t) => (
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
          <label style={{ flex: "0 0 240px" }}>
            벤더
            <select value={listVendor} onChange={(e) => go({ vendor: Number(e.target.value) || "" })}>
              <option value="">전체 벤더</option>
              {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </label>
          {isAdmin && (
            <label style={{ flex: "0 0 240px" }}>
              등록자
              <select value={author} onChange={(e) => go({ author: Number(e.target.value) || "" })}>
                <option value="">전체 등록자</option>
                {authors.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
              </select>
            </label>
          )}
        </div>
        {/* 문서 탭은 분석 화면이 아니므로 상태 열을 두지 않는다 */}
        <DocumentTable query={query} showGuideKind={docType === "guide"} showStatus={false} />
      </section>
    </>
  );
}

/** 문서 목록에서 (id, 이름) 선택지를 중복 없이 이름순으로 뽑는다. */
export function uniqueOptions(docs: DocumentSummary[], pick: (d: DocumentSummary) => [number, string] | null): [number, string][] {
  const map = new Map<number, string>();
  for (const d of docs) {
    const option = pick(d);
    if (option) map.set(option[0], option[1]);
  }
  return [...map.entries()].sort((a, b) => a[1].localeCompare(b[1], "ko"));
}

/** 문서 표 (문서 화면의 종류별 탭과 가이드 화면이 함께 쓴다). query 는 /documents 목록 API 의 검색 조건. */
export function DocumentTable({
  query, showGuideKind = false, showStatus = true, showDocType = false, readOnly = false,
}: { query: string; showGuideKind?: boolean; showStatus?: boolean; showDocType?: boolean; readOnly?: boolean }) {
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
  // 삭제(휴지통으로 이동)는 관리자 또는 같은 조직 문서만 (공유받거나 도메인 권한으로 보는 문서는 읽기 전용)
  const canDelete = (d: DocumentSummary) => !readOnly && (isAdmin || (d.access === "own" && d.partner_id != null && d.partner_id === me?.partner_id));
  const canDeleteAny = docs.data.some(canDelete);
  return (
    <div className="table-wrap">
      {remove.error && <p className="error">{remove.error.message}</p>}
      {downloading && <DownloadDialog doc={downloading} onClose={() => setDownloading(null)} />}
      <table style={{ minWidth: 900 }}>
        <thead>
          <tr>
            <th>문서 이름</th>
            {showDocType && <th>문서 목적</th>}
            {showGuideKind && <th>가이드 종류</th>}
            <th>설명</th><th>벤더</th><th>제품</th><th>등록자</th><th>등록 날짜</th><th>형식·분량</th>
            {showStatus && <th>상태</th>}
            <th>다운로드</th>
            {canDeleteAny && <th>삭제</th>}
          </tr>
        </thead>
        <tbody>
          {docs.data.map((d) => (
            <tr key={d.id}>
              <td>
                <Link to={`/documents/${d.id}`}>{d.title ?? d.url ?? `문서 ${d.id}`}</Link>
                {d.access === "shared" && <span className="badge granted" style={{ marginLeft: 6 }} title="다른 조직이 공유한 문서 (읽기 전용)">공유받음</span>}
                {d.access === "domain" && <span className="badge granted" style={{ marginLeft: 6 }} title="도메인 권한으로 열람 (읽기 전용)">도메인 열람</span>}
              </td>
              {showDocType && <td style={{ whiteSpace: "nowrap" }}>{docTypeLabel(d.doc_type)}</td>}
              {showGuideKind && (
                <td style={{ whiteSpace: "nowrap" }}>{GUIDE_KINDS.find((k) => k.key === d.guide_kind)?.label ?? "-"}</td>
              )}
              <td style={{ maxWidth: 280 }}>{d.description ?? <span className="muted">-</span>}</td>
              <td>{d.vendor_name}</td>
              <td>{productLabel(d.product, d.product_detail)}</td>
              <td style={{ whiteSpace: "nowrap" }}>{d.uploaded_by_name ?? "-"}</td>
              <td style={{ whiteSpace: "nowrap" }}>{new Date(d.created_at).toLocaleDateString()}</td>
              <td style={{ whiteSpace: "nowrap" }}>{d.source_type.toUpperCase()}{d.page_count ? ` · ${d.page_count}쪽` : ""}</td>
              {showStatus && <td><span className={`badge ${d.status}`}>{STATUS_LABELS[d.status]}</span></td>}
              <td>
                <button className="icon-button sm" title="다운로드" aria-label={`${d.title ?? "문서"} 다운로드`} onClick={() => setDownloading(d)}>
                  <DownloadIcon />
                </button>
              </td>
              {canDeleteAny && (
                <td>
                  {canDelete(d) && <button
                    className="icon-button sm danger"
                    title="삭제"
                    aria-label={`${d.title ?? "문서"} 삭제`}
                    disabled={remove.isPending}
                    onClick={() =>
                      window.confirm(`'${d.title ?? "문서"}' 문서를 삭제할까요?
휴지통으로 옮겨지며, 사용자 메뉴의 휴지통에서 언제든 원래대로 복구할 수 있습니다.`) &&
                      remove.mutate(d.id)
                    }
                  >
                    <TrashIcon />
                  </button>}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TrashIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 6h18" />
      <path d="M8 6V4h8v2" />
      <path d="M19 6l-1 14H6L5 6" />
      <path d="M10 11v6M14 11v6" />
    </svg>
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

/** 파일 형식: 규격서는 Excel 도, 기타 문서(제품 가격표·매입 금액)는 PDF·Word·Excel 만 (웹 주소 불가). */
const FILE_TYPES: Record<string, { accept: string; label: string }> = {
  spec: { accept: ".pdf,.docx,.xlsx,.pptx", label: "PDF, Word, Excel, PowerPoint" },
  price_list: { accept: ".pdf,.docx,.xlsx", label: "PDF, Word, Excel" },
  purchase: { accept: ".pdf,.docx,.xlsx", label: "PDF, Word, Excel" },
};
const DEFAULT_FILE_TYPE = { accept: ".pdf,.docx,.pptx", label: "PDF, Word, PowerPoint" };

/** 제품 가격표·매입 금액: 영업만 등록·조회 (관리자는 전부). 파일(PDF·Word·Excel)로만 받는다. */
const SALES_ONLY_TYPES: string[] = ["price_list", "purchase"];

function UploadForm({
  defaultType, allowed, onUploaded,
}: { defaultType: DocTypeKey; allowed: DocTypeKey[]; onUploaded: (type: DocTypeKey) => void }) {
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const vendors = me?.vendors ?? [];
  const [chosenType, setDocType] = useState<DocTypeKey>();
  const docType = chosenType ?? defaultType; // 고르기 전에는 지금 보고 있는 탭
  const sendType = docType;
  const fileType = FILE_TYPES[sendType] ?? DEFAULT_FILE_TYPE;
  const fileOnly = SALES_ONLY_TYPES.includes(sendType);
  const [guideKind, setGuideKind] = useState<GuideKindKey>("technical");
  const [vendorId, setVendorId] = useState<number | "">("");
  const [product, setProduct] = useState({ product: "", detail: "" });
  const [chosenMode, setMode] = useState<"file" | "url">("file");
  const mode = fileOnly ? "file" : chosenMode;
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [inputKey, setInputKey] = useState(0);

  const upload = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("vendor_id", String(vendorId));
      if (product.product) form.append("product", product.product);
      if (product.detail) form.append("product_detail", product.detail);
      form.append("doc_type", sendType);
      if (sendType === "guide") form.append("guide_kind", guideKind);
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
      {vendors.length === 0 ? (
        <p className="muted">접근 가능한 벤더 도메인이 없습니다. 관리자에게 도메인 지정을 요청하세요.</p>
      ) : (
        <form className="form" onSubmit={submit}>
          <div className="form-row">
            <label style={{ flex: "0 0 200px" }}>
              등록할 탭 (문서 종류)
              <select value={docType} onChange={(e) => setDocType(e.target.value as DocTypeKey)}>
                {DOC_TYPES.filter((t) => allowed.includes(t.key)).map((t) => <option key={t.key} value={t.key}>{t.full}</option>)}
              </select>
            </label>
            {sendType === "guide" && (
              <label style={{ flex: "0 0 180px" }}>
                가이드 종류
                <select value={guideKind} onChange={(e) => setGuideKind(e.target.value as GuideKindKey)}>
                  {GUIDE_KINDS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
                </select>
              </label>
            )}
            <label>
              벤더 도메인
              <select
                value={vendorId}
                onChange={(e) => {
                  setVendorId(Number(e.target.value) || "");
                  setProduct({ product: "", detail: "" });
                }}
                required
              >
                <option value="">선택</option>
                {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
            </label>
            <ProductSelect
              vendorName={vendors.find((v) => v.id === vendorId)?.name}
              product={product.product}
              detail={product.detail}
              onChange={(p, d) => setProduct({ product: p, detail: d })}
            />
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
            <label className="check"><input type="radio" checked={mode === "file"} onChange={() => setMode("file")} />파일 ({fileType.label})</label>
            {!fileOnly && <label className="check"><input type="radio" checked={mode === "url"} onChange={() => setMode("url")} />웹 문서 URL</label>}
          </div>
          {mode === "file" ? (
            <input key={`${inputKey}-${sendType}`} type="file" accept={fileType.accept} onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
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
