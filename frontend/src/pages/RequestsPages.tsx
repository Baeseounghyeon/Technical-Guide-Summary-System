import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, download } from "../api";
import { STATUS_LABELS, languageLabel } from "../labels";

interface RequestRow {
  guide_id: number;
  document_id: number;
  document_title: string | null;
  vendor_name: string;
  partner_name: string | null;
  target_language: string;
  status: string;
  approved: number;
  total: number;
  requested_by_name: string | null;
  created_at: string;
  exports: { id: number; format: string; doc_version: string }[];
}

const FORMAT_LABELS: Record<string, string> = { docx: "Word", pptx: "PPT" };

/** 내 요청 사항: 내가 요약을 요청한 문서. 상단 '문서' 메뉴와 사용자 메뉴에서 같은 화면으로 온다. */
export function MyRequestsPage() {
  return (
    <>
      <div className="page-header">
        <h1>내 요청 사항</h1>
        <p className="muted">내가 요약을 요청한 문서입니다. 문서 이름을 누르면 요약 가이드에서 검토를 이어 갈 수 있습니다.</p>
      </div>
      <RequestTable path="/my-requests" showRequester={false} empty="아직 요약을 요청한 문서가 없습니다." />
    </>
  );
}

/** 조직 요청 가이드: 같은 조직(회사) 사람들이 요약을 요청한 문서. 같은 조직이면 최종 문서를 내려받을 수 있다. */
export function OrgGuidesPage() {
  return (
    <>
      <div className="page-header">
        <h1>조직 요청 가이드</h1>
        <p className="muted">같은 조직에서 요약을 요청한 문서입니다. 최종 문서(Word·PowerPoint)가 만들어진 것은 바로 내려받을 수 있습니다.</p>
      </div>
      <RequestTable path="/org-guides" showRequester empty="조직에서 요약을 요청한 문서가 없습니다." />
    </>
  );
}

function RequestTable({ path, showRequester, empty }: { path: string; showRequester: boolean; empty: string }) {
  const rows = useQuery({
    queryKey: ["requests", path],
    queryFn: () => api<RequestRow[]>(path),
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === "queued" || r.status === "summarizing") ? 5000 : false),
  });
  return (
    <section className="card">
      {rows.isLoading && <p className="muted">불러오는 중…</p>}
      {rows.error && <p className="error">{rows.error.message}</p>}
      {rows.data?.length === 0 && <p className="muted">{empty}</p>}
      {!!rows.data?.length && (
        <div className="table-wrap">
          <table style={{ minWidth: 860 }}>
            <thead>
              <tr>
                <th>문서 이름</th><th>벤더</th><th>요약 언어</th>
                {showRequester && <th>요청자</th>}
                <th>요청 날짜</th><th>진행</th><th>최종 문서 다운로드</th>
              </tr>
            </thead>
            <tbody>
              {rows.data.map((r) => {
                const pct = r.total ? Math.round((r.approved / r.total) * 100) : 0;
                return (
                  <tr key={r.guide_id}>
                    <td><Link to={`/guides/${r.guide_id}`}>{r.document_title ?? `문서 ${r.document_id}`}</Link></td>
                    <td>{r.vendor_name}</td>
                    <td>{languageLabel(r.target_language)}</td>
                    {showRequester && <td>{r.requested_by_name ?? "-"}</td>}
                    <td>{new Date(r.created_at).toLocaleDateString()}</td>
                    <td>
                      <span className={`badge ${r.status}`}>{STATUS_LABELS[r.status] ?? r.status}</span>
                      {r.total > 0 && (
                        <>
                          <div className="progress" style={{ margin: "6px 0 2px" }}><div style={{ width: `${pct}%`, background: "var(--ok)" }} /></div>
                          <span className="muted">승인 {r.approved}/{r.total}</span>
                        </>
                      )}
                    </td>
                    <td>
                      {r.exports.length === 0 ? (
                        <span className="muted">아직 없음</span>
                      ) : (
                        <div className="actions">
                          {r.exports.map((e) => (
                            <button key={e.id} className="link" onClick={() => download(`/exports/${e.id}/download`)}>
                              {FORMAT_LABELS[e.format] ?? e.format} v{e.doc_version}
                            </button>
                          ))}
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
