import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
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

type Filter = "all" | "done" | "progress" | "failed";

export default function DashboardPage() {
  const [filter, setFilter] = useState<Filter>("all");
  const data = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardData>("/dashboard"),
    // 분석·요약이 진행 중이면 주기적으로 새로 고친다.
    refetchInterval: (q) => (q.state.data?.documents.some((d) => d.stage === "analyzing" || d.stage === "summarizing") ? 3000 : false),
  });

  const c = data.data?.counts;
  const docs = (data.data?.documents ?? []).filter((d) => filter === "all" || STAGES[d.stage].group === filter);
  const cards: { key: Filter; label: string; value?: number; tone: string; note?: string }[] = [
    { key: "all", label: "처리한 문서", value: c?.total, tone: "accent" },
    { key: "done", label: "처리 완료", value: c?.completed, tone: "ok", note: "요약 승인 완료" },
    { key: "progress", label: "처리 미완료", value: c?.in_progress, tone: "warn", note: c?.pending_reviews ? `검토 대기 항목 ${c.pending_reviews}개` : "분석·요약·검토 중" },
    { key: "failed", label: "실패", value: c?.failed, tone: "danger", note: "분석 실패" },
  ];

  return (
    <>
      <section className="navy-band">
        <div className="band-inner">
          <div className="section-head">
            <h2 className="section-title">내 처리 현황</h2>
            <Link to="/documents" className="button-link on-navy small">+ 새 문서 올리기</Link>
          </div>

          <div className="stat-grid">
            {cards.map((card) => (
              <button
                key={card.key}
                className={`stat-card tone-${card.tone} ${filter === card.key ? "selected" : ""}`}
                onClick={() => setFilter(card.key)}
              >
                <span className="stat-label">{card.label}</span>
                <span className="stat-value">{card.value ?? "–"}</span>
                {card.note && <span className="stat-note">{card.note}</span>}
              </button>
            ))}
            <div className="stat-card tone-plain">
              <span className="stat-label">생성한 최종 문서</span>
              <span className="stat-value">{c?.exports ?? "–"}</span>
              <span className="stat-note">Word · PowerPoint</span>
            </div>
          </div>
        </div>
      </section>

      <section className="card">
        <div className="summary-head">
          <h2 style={{ margin: 0 }}>
            {filter === "all" ? "전체 문서" : filter === "done" ? "처리 완료 문서" : filter === "progress" ? "처리 미완료 문서" : "실패한 문서"}
          </h2>
          <span className="muted">{docs.length}건</span>
        </div>
        {data.isLoading && <p className="muted">불러오는 중…</p>}
        {data.error && <p className="error">{data.error.message}</p>}
        {data.data && docs.length === 0 && (
          <p className="muted">
            {filter === "all" ? <>아직 올린 문서가 없습니다. <Link to="/documents">문서 올리기</Link></> : "해당하는 문서가 없습니다."}
          </p>
        )}
        {docs.length > 0 && (
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
