import { Fragment, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, download } from "../api";
import { useAuth } from "../auth";
import { languageLabel, STATUS_LABELS, type ExtraKindKey } from "../labels";
import { productLabel } from "../ProductSelect";
import { TrashIcon } from "./DocumentsPage";
import type { DocumentSummary } from "../types";

interface Generated {
  id: number;
  title: string;
  fields: { domain?: string | null };
  formats: string[];
  root_id: number;
  attachments: { kind: ExtraKindKey; label: string; document_id: number; title: string | null }[];
  created_by_name: string;
  created_at: string;
}
export const FORMAT_LABELS: Record<string, string> = { pdf: "PDF", docx: "Word", xlsx: "Excel" };

/** 생성한 견적서: 견적서별 최신 버전, 엑셀·PDF 받기, 삭제. */
export function GeneratedListPage() {
  const rows = useQuery({ queryKey: ["generated", "quote"], queryFn: () => api<Generated[]>("/generated?doc_type=quote") });
  const queryClient = useQueryClient();
  // 삭제: 같은 이력(모든 버전)을 함께 지운다
  const remove = useMutation({
    mutationFn: (id: number) => api(`/generated/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["generated", "quote"] }),
  });
  // 이력(root_id)별로 묶는다. 목록은 최신순이므로 첫 항목이 최신 버전.
  const latest = new Map<number, Generated>();
  for (const g of rows.data ?? []) if (!latest.has(g.root_id)) latest.set(g.root_id, g);
  // 견적서에 쓴 가격표·매입 금액 문서는 원본 그대로 받는다
  const attachmentCell = (g: Generated) =>
    g.attachments.length ? (
      <div className="actions">
        {g.attachments.map((a) => (
          <button key={`${a.kind}-${a.document_id}`} className="link" title={`${a.label} 원본 받기`} onClick={() => download(`/documents/${a.document_id}/download?format=original`)}>
            {a.label}: {a.title ?? `문서 ${a.document_id}`}
          </button>
        ))}
      </div>
    ) : (
      <span className="muted">-</span>
    );

  return (
    <>
      <div className="page-header">
        <h1>생성한 견적서</h1>
        <p className="muted">
          견적서 생성에서 만든 견적서입니다. 엑셀·PDF로 받거나 삭제할 수 있습니다. 새로 만들려면 <Link to="/quotes/create">견적서 생성</Link>으로 가세요.
        </p>
      </div>
      <section className="card">
        {rows.isLoading && <p className="muted">불러오는 중…</p>}
        {rows.error && <p className="error">{rows.error.message}</p>}
        {rows.data?.length === 0 && <p className="muted">아직 생성한 견적서가 없습니다.</p>}
        {remove.error && <p className="error">{remove.error.message}</p>}
        {latest.size > 0 && (
          <div className="table-wrap">
            <table className="quote-list" style={{ minWidth: 900 }}>
              <thead>
                <tr><th style={{ width: 80 }}>도메인</th><th style={{ width: "24%" }}>문서 제목</th><th>가격표·매입 금액</th><th style={{ width: 90 }}>작성자</th><th style={{ width: 170 }}>최종 생성 일시</th><th style={{ width: 110 }}>다운로드</th><th style={{ width: 64 }}>삭제</th></tr>
              </thead>
              <tbody>
                {[...latest.entries()].map(([root, g]) => (
                  <tr key={root}>
                    <td>{g.fields.domain ?? "Thales"}</td>
                    <td><strong>{g.title}</strong></td>
                    <td className="attach-list">{attachmentCell(g)}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{g.created_by_name}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{new Date(g.created_at).toLocaleString()}</td>
                    <td>
                      <div className="actions">
                        {g.formats.map((f) => (
                          <button key={f} className="link" onClick={() => download(`/generated/${g.id}/download?format=${f}`)}>{FORMAT_LABELS[f] ?? f}</button>
                        ))}
                      </div>
                    </td>
                    <td>
                      <button
                        className="icon-button sm danger"
                        title="삭제"
                        aria-label={`${g.title} 삭제`}
                        disabled={remove.isPending}
                        onClick={() => window.confirm(`'${g.title}'을(를) 삭제할까요? 이 견적서의 모든 버전이 함께 지워집니다.`) && remove.mutate(g.id)}
                      >
                        <TrashIcon />
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
          등록한 가이드 문서를 골라 요약 가이드를 만듭니다. 새 문서는 <Link to="/documents?type=guide">문서 등록</Link>에서 먼저 올리세요.
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
