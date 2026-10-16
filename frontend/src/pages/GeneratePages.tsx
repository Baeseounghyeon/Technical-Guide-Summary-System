import { Fragment, useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, download, postBlob } from "../api";
import { useAuth } from "../auth";
import { languageLabel, STATUS_LABELS } from "../labels";
import { productLabel } from "../ProductSelect";
import type { DocumentSummary } from "../types";

export type FormType = "spec" | "quote";
const KIND: Record<FormType, { label: string; base: string }> = {
  spec: { label: "규격서", base: "/specs" },
  quote: { label: "견적서", base: "/quotes" },
};
type Field = { key: string; label: string; hint: string; wide: boolean };
interface Generated {
  id: number;
  doc_type: FormType;
  title: string;
  fields: Record<string, string>;
  version: number;
  root_id: number;
  based_on_id: number | null;
  source_document_id: number | null;
  source_document_title: string | null;
  created_by_name: string;
  partner_name: string | null;
  created_at: string;
}
type Format = "pdf" | "docx";
const FORMATS: { key: Format; label: string }[] = [
  { key: "pdf", label: "PDF" },
  { key: "docx", label: "Word" },
];

/** 규격서·견적서 생성: 재사용할 문서를 체크하면 필수 입력값이 채워지고, 고쳐서 새 문서를 만든다.
 *  ?from=<생성 문서 id> 로 오면 그 문서를 고쳐 다음 버전을 만든다 ('생성한 ○○'의 수정). */
export function FormCreatePage({ docType }: { docType: FormType }) {
  const { label, base } = KIND[docType];
  const [params] = useSearchParams();
  const fromId = Number(params.get("from")) || null;
  const queryClient = useQueryClient();
  const fields = useQuery({ queryKey: ["form-fields", docType], queryFn: () => api<Field[]>(`/forms/${docType}/fields`) });
  const [tab, setTab] = useState<"registered" | "generated">(fromId ? "generated" : "registered");
  const [title, setTitle] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [sourceId, setSourceId] = useState<number | null>(null);
  const [basedOn, setBasedOn] = useState<Generated | null>(null);
  const [format, setFormat] = useState<Format>("pdf");
  const [preview, setPreview] = useState<string | null>(null);
  const [created, setCreated] = useState<Generated | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reset = () => {
    setTitle("");
    setValues({});
    setSourceId(null);
    setBasedOn(null);
  };
  const applyGenerated = (g: Generated) => {
    setTitle(g.title);
    setValues(g.fields);
    setSourceId(g.source_document_id);
    setBasedOn(g);
    setCreated(null);
  };
  // '생성한 ○○'에서 수정으로 오면 그 문서를 불러온다
  useEffect(() => {
    if (fromId) api<Generated>(`/generated/${fromId}`).then(applyGenerated, (e: Error) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromId]);

  const pickRegistered = async (d: DocumentSummary) => {
    setError(null);
    setCreated(null);
    if (sourceId === d.id && !basedOn) return reset();
    try {
      const filled = await api<{ title: string; fields: Record<string, string> }>(`/forms/${docType}/prefill?document_id=${d.id}`);
      setTitle(filled.title);
      setValues(filled.fields);
      setSourceId(d.id);
      setBasedOn(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const pickGenerated = (g: Generated) => {
    setError(null);
    if (basedOn?.id === g.id) return reset();
    applyGenerated(g);
  };

  const body = () => ({ doc_type: docType, title, fields: values, source_document_id: sourceId, based_on_id: basedOn?.id ?? null });
  const missing = (fields.data ?? []).filter((f) => !values[f.key]?.trim()).map((f) => f.label);
  if (!title.trim()) missing.unshift("문서 제목");

  const showPreview = useMutation({
    mutationFn: () => postBlob("/forms/preview", body()),
    onSuccess: (blob) => setPreview(URL.createObjectURL(blob)),
  });
  const create = useMutation({
    mutationFn: () => api<Generated>("/generated", { method: "POST", json: body() }),
    onSuccess: async (g) => {
      setCreated(g);
      queryClient.invalidateQueries({ queryKey: ["generated", docType] });
      await download(`/generated/${g.id}/download?format=${format}`);
    },
  });

  return (
    <>
      <div className="page-header">
        <h1>{label} 생성</h1>
        <p className="muted">
          재사용할 {label}를 체크하면 그 내용이 필수 입력 항목에 채워집니다. 내용을 고친 뒤 미리보기로 확인하고 생성하세요(PDF·Word).
          만든 문서는 <Link to={`${base}/created`}>생성한 {label}</Link>에서 이력과 함께 봅니다.
        </p>
      </div>

      <section className="card">
        <h2 className="section-title">재사용할 {label}</h2>
        <div className="filters">
          <button className={tab === "registered" ? "active" : ""} onClick={() => setTab("registered")}>등록한 {label}</button>
          <button className={tab === "generated" ? "active" : ""} onClick={() => setTab("generated")}>생성한 {label}</button>
        </div>
        {tab === "registered" ? (
          <RegisteredPicker docType={docType} checked={basedOn ? null : sourceId} onPick={pickRegistered} />
        ) : (
          <GeneratedPicker docType={docType} checked={basedOn?.id ?? null} onPick={pickGenerated} />
        )}
        <p className="muted" style={{ marginTop: 8 }}>
          {basedOn
            ? `'${basedOn.title}' v${basedOn.version}을(를) 불러왔습니다. 고쳐서 생성하면 같은 문서 이력의 다음 버전이 됩니다.`
            : sourceId
              ? `체크한 ${label}의 내용으로 채웠습니다. 고친 뒤 새 문서로 만듭니다.`
              : "체크하지 않으면 빈 양식에서 새로 작성합니다."}
        </p>
      </section>

      <section className="card">
        <div className="gen-form">
          <div className="gen-bar">{label} 정보 (필수 입력)</div>
          <label className="gen-wide">
            <span>문서 제목 <span className="required">*</span></span>
            <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder={`예: ○○ 도입 ${label}`} />
          </label>
          <div className="gen-grid">
            {fields.data?.map((f) => (
              <label key={f.key} className={f.wide ? "gen-wide" : ""}>
                <span>{f.label} <span className="required">*</span></span>
                {f.wide ? (
                  <textarea rows={5} value={values[f.key] ?? ""} placeholder={f.hint} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} />
                ) : (
                  <input value={values[f.key] ?? ""} placeholder={f.hint} onChange={(e) => setValues({ ...values, [f.key]: e.target.value })} />
                )}
              </label>
            ))}
          </div>
        </div>
        {error && <p className="error">{error}</p>}
        {(showPreview.error || create.error) && <p className="error">{(showPreview.error ?? create.error)!.message}</p>}
        {missing.length > 0 && <p className="muted">아직 비어 있는 항목: {missing.join(", ")}</p>}
        <div className="actions" style={{ marginTop: 14, alignItems: "center" }}>
          <span className="muted">형식</span>
          {FORMATS.map((f) => (
            <label key={f.key} className="check">
              <input type="radio" name="format" checked={format === f.key} onChange={() => setFormat(f.key)} /> {f.label}
            </label>
          ))}
          <button disabled={showPreview.isPending} onClick={() => showPreview.mutate()}>미리보기</button>
          <button className="primary" disabled={create.isPending || missing.length > 0} onClick={() => create.mutate()}>
            {create.isPending ? "생성 중…" : "생성"}
          </button>
        </div>
        {created && (
          <div className="notice" style={{ marginTop: 14 }}>
            <strong>'{created.title}' v{created.version}을(를) 만들었습니다.</strong>
            <div className="actions" style={{ marginTop: 8 }}>
              {FORMATS.map((f) => (
                <button key={f.key} className="link" onClick={() => download(`/generated/${created.id}/download?format=${f.key}`)}>{f.label} 받기</button>
              ))}
              <Link to={`${base}/created`}>생성한 {label} 보기</Link>
            </div>
          </div>
        )}
      </section>
      {preview && <PreviewModal url={preview} onClose={() => { URL.revokeObjectURL(preview); setPreview(null); }} />}
    </>
  );
}

function RegisteredPicker({ docType, checked, onPick }: { docType: FormType; checked: number | null; onPick: (d: DocumentSummary) => void }) {
  const docs = useQuery({ queryKey: ["documents", `doc_type=${docType}`], queryFn: () => api<DocumentSummary[]>(`/documents?doc_type=${docType}`) });
  if (docs.isLoading) return <p className="muted">불러오는 중…</p>;
  if (docs.error) return <p className="error">{docs.error.message}</p>;
  if (!docs.data?.length) return <p className="muted">등록한 {KIND[docType].label}가 없습니다. <Link to={`/documents?type=${docType}`}>문서 등록</Link>에서 올리면 여기서 재사용할 수 있습니다.</p>;
  return (
    <div className="table-wrap">
      <table style={{ minWidth: 760 }}>
        <thead><tr><th style={{ width: 48 }}>선택</th><th>문서 이름</th><th>벤더</th><th>제품</th><th>등록자</th><th>등록 일자</th><th>상태</th></tr></thead>
        <tbody>
          {docs.data.map((d) => {
            const ready = d.status === "parsed";
            return (
              <tr key={d.id} className={checked === d.id ? "highlight" : ""}>
                <td>
                  <input type="checkbox" aria-label={`${d.title ?? "문서"} 재사용`} disabled={!ready} checked={checked === d.id} onChange={() => onPick(d)} />
                </td>
                <td>{d.title ?? d.url ?? `문서 ${d.id}`}</td>
                <td>{d.vendor_name}</td>
                <td>{productLabel(d.product, d.product_detail)}</td>
                <td>{d.uploaded_by_name ?? "-"}</td>
                <td style={{ whiteSpace: "nowrap" }}>{new Date(d.created_at).toLocaleDateString()}</td>
                <td>{ready ? "재사용 가능" : STATUS_LABELS[d.status] ?? d.status}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function GeneratedPicker({ docType, checked, onPick }: { docType: FormType; checked: number | null; onPick: (g: Generated) => void }) {
  const rows = useQuery({ queryKey: ["generated", docType], queryFn: () => api<Generated[]>(`/generated?doc_type=${docType}`) });
  if (rows.isLoading) return <p className="muted">불러오는 중…</p>;
  if (rows.error) return <p className="error">{rows.error.message}</p>;
  if (!rows.data?.length) return <p className="muted">아직 생성한 {KIND[docType].label}가 없습니다.</p>;
  return (
    <div className="table-wrap">
      <table style={{ minWidth: 640 }}>
        <thead><tr><th style={{ width: 48 }}>선택</th><th>문서 제목</th><th>버전</th><th>재사용 원본</th><th>생성 일시</th></tr></thead>
        <tbody>
          {rows.data.map((g) => (
            <tr key={g.id} className={checked === g.id ? "highlight" : ""}>
              <td><input type="checkbox" aria-label={`${g.title} v${g.version} 재사용`} checked={checked === g.id} onChange={() => onPick(g)} /></td>
              <td>{g.title}</td>
              <td>v{g.version}</td>
              <td>{g.source_document_title ?? "-"}</td>
              <td style={{ whiteSpace: "nowrap" }}>{new Date(g.created_at).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PreviewModal({ url, onClose }: { url: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal preview-modal" role="dialog" aria-modal="true" aria-label="미리보기">
        <div className="summary-head">
          <h2 style={{ margin: 0 }}>미리보기</h2>
          <button className="link" onClick={onClose}>닫기</button>
        </div>
        <iframe title="미리보기 PDF" src={url} className="preview-frame" />
      </div>
    </div>
  );
}

/** 생성한 규격서·견적서: 문서별 최신 버전과 이력(버전마다 PDF·Word 받기, 고쳐서 다음 버전 만들기). */
export function GeneratedListPage({ docType }: { docType: FormType }) {
  const { label, base } = KIND[docType];
  const navigate = useNavigate();
  const rows = useQuery({ queryKey: ["generated", docType], queryFn: () => api<Generated[]>(`/generated?doc_type=${docType}`) });
  const [open, setOpen] = useState<Set<number>>(new Set());
  // 이력(root_id)별로 묶는다. 목록은 최신순이므로 첫 항목이 최신 버전.
  const groups = new Map<number, Generated[]>();
  for (const g of rows.data ?? []) groups.set(g.root_id, [...(groups.get(g.root_id) ?? []), g]);
  const toggle = (id: number) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const downloads = (g: Generated) => (
    <div className="actions">
      {FORMATS.map((f) => (
        <button key={f.key} className="link" onClick={() => download(`/generated/${g.id}/download?format=${f.key}`)}>{f.label}</button>
      ))}
    </div>
  );

  return (
    <>
      <div className="page-header">
        <h1>생성한 {label}</h1>
        <p className="muted">
          {label} 생성에서 만든 문서입니다. 고쳐서 다시 만들면 같은 문서의 다음 버전으로 이력이 쌓입니다. 새로 만들려면 <Link to={`${base}/create`}>{label} 생성</Link>으로 가세요.
        </p>
      </div>
      <section className="card">
        {rows.isLoading && <p className="muted">불러오는 중…</p>}
        {rows.error && <p className="error">{rows.error.message}</p>}
        {rows.data?.length === 0 && <p className="muted">아직 생성한 {label}가 없습니다.</p>}
        {groups.size > 0 && (
          <div className="table-wrap">
            <table style={{ minWidth: 900 }}>
              <thead>
                <tr><th>문서 제목</th><th>최신 버전</th><th>재사용 원본</th><th>작성자</th><th>최종 생성 일시</th><th>다운로드</th><th>관리</th></tr>
              </thead>
              <tbody>
                {[...groups.entries()].map(([root, versions]) => {
                  const latest = versions[0];
                  return (
                    <Fragment key={root}>
                      <tr>
                        <td><strong>{latest.title}</strong></td>
                        <td>v{latest.version}</td>
                        <td>{latest.source_document_title ?? "-"}</td>
                        <td>{latest.created_by_name}</td>
                        <td style={{ whiteSpace: "nowrap" }}>{new Date(latest.created_at).toLocaleString()}</td>
                        <td>{downloads(latest)}</td>
                        <td style={{ whiteSpace: "nowrap" }}>
                          <div className="actions">
                            <button className="link" onClick={() => navigate(`${base}/create?from=${latest.id}`)}>수정해서 새 버전</button>
                            <button className="link" onClick={() => toggle(root)}>{open.has(root) ? "이력 닫기" : `이력 ${versions.length}건`}</button>
                          </div>
                        </td>
                      </tr>
                      {open.has(root) &&
                        versions.map((g) => (
                          <tr key={g.id} className="history-row">
                            <td className="muted">└ v{g.version} {g.title !== latest.title ? `· ${g.title}` : ""}</td>
                            <td>v{g.version}</td>
                            <td>{g.source_document_title ?? "-"}</td>
                            <td>{g.created_by_name}</td>
                            <td style={{ whiteSpace: "nowrap" }}>{new Date(g.created_at).toLocaleString()}</td>
                            <td>{downloads(g)}</td>
                            <td><button className="link" onClick={() => navigate(`${base}/create?from=${g.id}`)}>이 버전으로 수정</button></td>
                          </tr>
                        ))}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

// ---------- 가이드 생성 / 생성한 가이드 ----------

/** 가이드 생성: 등록한 가이드 문서를 골라 요약 가이드를 만든다 (문서 화면에서 언어를 골라 요약 시작). */
export function GuideCreatePage() {
  const { me } = useAuth();
  const query = me?.role === "platform_admin" ? "doc_type=guide" : `doc_type=guide&uploaded_by=${me?.id}`;
  const docs = useQuery({ queryKey: ["documents", query], queryFn: () => api<DocumentSummary[]>(`/documents?${query}`), enabled: !!me });
  return (
    <>
      <div className="page-header">
        <h1>가이드 생성</h1>
        <p className="muted">
          등록한 가이드 문서를 골라 요약 가이드를 만듭니다. 새 문서는 <Link to="/documents?type=guide">가이드 등록</Link>에서 먼저 올리세요.
          만든 가이드는 <Link to="/guides/created">생성한 가이드</Link>에서 봅니다.
        </p>
      </div>
      <section className="card">
        {docs.isLoading && <p className="muted">불러오는 중…</p>}
        {docs.error && <p className="error">{docs.error.message}</p>}
        {docs.data?.length === 0 && <p className="muted">등록한 가이드 문서가 없습니다.</p>}
        {!!docs.data?.length && (
          <div className="table-wrap">
            <table style={{ minWidth: 760 }}>
              <thead><tr><th>문서 이름</th><th>벤더</th><th>제품</th><th>등록 일자</th><th>상태</th><th>가이드 만들기</th></tr></thead>
              <tbody>
                {docs.data.map((d) => (
                  <tr key={d.id}>
                    <td>{d.title ?? d.url ?? `문서 ${d.id}`}</td>
                    <td>{d.vendor_name}</td>
                    <td>{productLabel(d.product, d.product_detail)}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{new Date(d.created_at).toLocaleDateString()}</td>
                    <td>{STATUS_LABELS[d.status] ?? d.status}</td>
                    <td>
                      {d.status === "parsed" ? <Link to={`/documents/${d.id}`}>요약 가이드 만들기</Link> : <span className="muted">분석 후 가능</span>}
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

interface MyGuide {
  id: number;
  document_id: number;
  document_title: string;
  vendor_name: string;
  product: string | null;
  product_detail: string | null;
  target_language: string;
  status: string;
  created_at: string;
  exports: { id: number; format: string; doc_version: string; status: string; created_at: string }[];
}

/** 생성한 가이드: 내가 만든 요약 가이드와 최종 문서(Word·PowerPoint) 생성 이력. */
export function CreatedGuidesPage() {
  const rows = useQuery({ queryKey: ["my-guides"], queryFn: () => api<MyGuide[]>("/my-guides") });
  const [open, setOpen] = useState<number | null>(null);
  const FORMAT: Record<string, string> = { docx: "Word", pptx: "PowerPoint" };
  return (
    <>
      <div className="page-header">
        <h1>생성한 가이드</h1>
        <p className="muted">내가 만든 요약 가이드입니다. 이력을 펼치면 만든 최종 문서(Word·PowerPoint)를 버전별로 받을 수 있습니다.</p>
      </div>
      <section className="card">
        {rows.isLoading && <p className="muted">불러오는 중…</p>}
        {rows.error && <p className="error">{rows.error.message}</p>}
        {rows.data?.length === 0 && <p className="muted">아직 생성한 가이드가 없습니다. <Link to="/guides/create">가이드 생성</Link>에서 만드세요.</p>}
        {!!rows.data?.length && (
          <div className="table-wrap">
            <table style={{ minWidth: 860 }}>
              <thead><tr><th>문서 이름</th><th>벤더</th><th>제품</th><th>요약 언어</th><th>상태</th><th>생성 일시</th><th>최종 문서 이력</th></tr></thead>
              <tbody>
                {rows.data.map((g) => (
                  <Fragment key={g.id}>
                    <tr>
                      <td><Link to={`/guides/${g.id}`}><strong>{g.document_title}</strong></Link></td>
                      <td>{g.vendor_name}</td>
                      <td>{productLabel(g.product, g.product_detail)}</td>
                      <td>{languageLabel(g.target_language)}</td>
                      <td>{STATUS_LABELS[g.status] ?? g.status}</td>
                      <td style={{ whiteSpace: "nowrap" }}>{new Date(g.created_at).toLocaleString()}</td>
                      <td>
                        {g.exports.length ? (
                          <button className="link" onClick={() => setOpen(open === g.id ? null : g.id)}>{open === g.id ? "이력 닫기" : `${g.exports.length}건`}</button>
                        ) : (
                          <span className="muted">-</span>
                        )}
                      </td>
                    </tr>
                    {open === g.id &&
                      g.exports.map((e) => (
                        <tr key={e.id} className="history-row">
                          <td className="muted">└ v{e.doc_version}</td>
                          <td colSpan={2}>{FORMAT[e.format] ?? e.format}</td>
                          <td colSpan={2}>{STATUS_LABELS[e.status] ?? e.status}</td>
                          <td style={{ whiteSpace: "nowrap" }}>{new Date(e.created_at).toLocaleString()}</td>
                          <td>{e.status === "done" && <button className="link" onClick={() => download(`/exports/${e.id}/download`)}>받기</button>}</td>
                        </tr>
                      ))}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
