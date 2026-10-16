import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, download } from "../api";
import { languageLabel } from "../labels";
import type { DashboardData, DocumentStage } from "../types";

const STAGES: Record<DocumentStage, { label: string; badge: string; group: "done" | "progress" | "failed" }> = {
  analyzing: { label: "분석 중", badge: "parsing", group: "progress" },
  not_started: { label: "요약 전", badge: "", group: "progress" },
  summarizing: { label: "요약 중", badge: "summarizing", group: "progress" },
  reviewing: { label: "검토 중", badge: "reviewing", group: "progress" },
  approved: { label: "승인 완료", badge: "approved", group: "done" },
  exported: { label: "문서 생성 완료", badge: "done", group: "done" },
  failed: { label: "분석 실패", badge: "failed", group: "failed" },
};

/** 홈 '내 처리 현황' 카드별 화면 */
export const HOME_VIEWS = {
  processed: { title: "처리한 문서", note: "내가 올린 모든 문서와 진행 단계입니다." },
  done: { title: "처리 완료", note: "요약을 모두 승인한 문서입니다. 최종 문서(Word·PowerPoint)를 만들 수 있습니다." },
  progress: { title: "처리 미완료", note: "분석 중이거나 요약 전·요약 중·검토 중인 문서입니다." },
  failed: { title: "실패", note: "목차 분석에 실패한 문서입니다. 스캔 이미지 PDF 이거나 파일이 손상되었을 수 있습니다." },
  exports: { title: "생성한 최종 문서", note: "요약 가이드에서 만든 최종 문서(Word·PowerPoint)입니다. 바로 내려받을 수 있습니다." },
} as const;
export type HomeView = keyof typeof HOME_VIEWS;

const FORMAT_LABELS: Record<string, string> = { docx: "Word", pptx: "PowerPoint" };

export default function HomeDetailPage() {
  const view = (useParams().view ?? "processed") as HomeView;
  const meta = HOME_VIEWS[view] ?? HOME_VIEWS.processed;
  const data = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardData>("/dashboard"),
    refetchInterval: (q) => (q.state.data?.documents.some((d) => d.stage === "analyzing" || d.stage === "summarizing") ? 3000 : false),
  });
  const docs = (data.data?.documents ?? []).filter((d) =>
    view === "processed" ? true : view === "exports" ? d.export_files.length > 0 : STAGES[d.stage].group === view,
  );

  return (
    <>
      <div className="page-header">
        <p className="muted"><Link to="/">홈</Link> / 내 처리 현황</p>
        <h1>{meta.title}</h1>
        <p className="muted">{meta.note}</p>
      </div>
      <div className="filters">
        {(Object.keys(HOME_VIEWS) as HomeView[]).map((k) => (
          <Link key={k} to={`/home/${k}`} className={`filter-link${k === view ? " active" : ""}`}>{HOME_VIEWS[k].title}</Link>
        ))}
      </div>
      <section className="card">
        {data.isLoading && <p className="muted">불러오는 중…</p>}
        {data.error && <p className="error">{data.error.message}</p>}
        {data.data && docs.length === 0 && <p className="muted">해당하는 문서가 없습니다.</p>}
        {docs.length > 0 && view === "exports" && (
          <div className="table-wrap">
            <table style={{ minWidth: 760 }}>
              <thead><tr><th>문서 이름</th><th>벤더</th><th>요약 언어</th><th>형식</th><th>버전</th><th>만든 날짜</th><th>다운로드</th></tr></thead>
              <tbody>
                {docs.flatMap((d) =>
                  d.export_files.map((e) => (
                    <tr key={e.id}>
                      <td><Link to={d.guide_id ? `/guides/${d.guide_id}` : `/documents/${d.id}`}>{d.title}</Link></td>
                      <td>{d.vendor_name}</td>
                      <td>{d.target_language ? languageLabel(d.target_language) : "-"}</td>
                      <td>{FORMAT_LABELS[e.format] ?? e.format}</td>
                      <td>v{e.doc_version}</td>
                      <td style={{ whiteSpace: "nowrap" }}>{new Date(e.created_at).toLocaleDateString()}</td>
                      <td><button className="link" onClick={() => download(`/exports/${e.id}/download`)}>내려받기</button></td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          </div>
        )}
        {docs.length > 0 && view !== "exports" && (
          <div className="table-wrap">
            <table style={{ minWidth: 860 }}>
              <thead>
                <tr><th>문서 이름</th><th>벤더</th><th>형식</th><th>등록일</th><th>진행 단계</th><th>요약 승인</th><th>최종 문서</th></tr>
              </thead>
              <tbody>
                {docs.map((d) => {
                  const stage = STAGES[d.stage];
                  const pct = d.total_sections ? Math.round((d.approved_sections / d.total_sections) * 100) : 0;
                  return (
                    <tr key={d.id}>
                      <td style={{ minWidth: 240 }}>
                        <Link to={d.guide_id ? `/guides/${d.guide_id}` : `/documents/${d.id}`}><strong>{d.title}</strong></Link>
                        {d.target_language && <div className="muted">{languageLabel(d.target_language)} 요약</div>}
                      </td>
                      <td>{d.vendor_name}</td>
                      <td style={{ whiteSpace: "nowrap" }}>{d.source_type.toUpperCase()}{d.page_count ? ` · ${d.page_count}쪽` : ""}</td>
                      <td style={{ whiteSpace: "nowrap" }}>{new Date(d.created_at).toLocaleDateString()}</td>
                      <td><span className={`badge ${stage.badge}`}>{stage.label}</span></td>
                      <td style={{ minWidth: 130 }}>
                        {d.total_sections ? (
                          <>
                            <div className="progress" style={{ margin: "4px 0" }}><div style={{ width: `${pct}%`, background: "var(--ok)" }} /></div>
                            <span className="muted">{d.approved_sections}/{d.total_sections}</span>
                          </>
                        ) : (
                          <span className="muted">-</span>
                        )}
                      </td>
                      <td>{d.exports ? `${d.exports}건` : <span className="muted">-</span>}</td>
                    </tr>
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
