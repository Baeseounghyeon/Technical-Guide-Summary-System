import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import Calendar from "../Calendar";
import type { DashboardData } from "../types";

export default function DashboardPage() {
  const data = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<DashboardData>("/dashboard"),
    // 분석·요약이 진행 중이면 주기적으로 새로 고친다.
    refetchInterval: (q) => (q.state.data?.documents.some((d) => d.stage === "analyzing" || d.stage === "summarizing") ? 3000 : false),
  });

  const c = data.data?.counts;
  const cards: { key: string; label: string; value?: number; tone: string; note?: string }[] = [
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
              <div key={card.key} className={`stat-card tone-${card.tone}`}>
                <span className="stat-label">{card.label}</span>
                <span className="stat-value">{card.value ?? "–"}</span>
                {card.note && <span className="stat-note">{card.note}</span>}
              </div>
            ))}
            <div className="stat-card tone-plain">
              <span className="stat-label">생성한 최종 문서</span>
              <span className="stat-value">{c?.exports ?? "–"}</span>
              <span className="stat-note">Word · PowerPoint</span>
            </div>
          </div>
        </div>
      </section>

      <Calendar />
    </>
  );
}
