import { useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { ACCESS_LABELS, GRANT_STATUS } from "../labels";
import type { AccessGrant, Domain } from "../types";

export default function CommunityPage() {
  const domains = useQuery({ queryKey: ["community-domains"], queryFn: () => api<Domain[]>("/community/domains") });
  const mine = useQuery({ queryKey: ["my-access-requests"], queryFn: () => api<AccessGrant[]>("/community/access-requests/mine") });

  const open = domains.data?.filter((d) => d.access !== "none") ?? [];
  const closed = domains.data?.filter((d) => d.access === "none") ?? [];

  return (
    <>
      <div className="page-header">
        <h1>커뮤니티</h1>
        <p className="muted">같은 벤더를 지원하는 파트너사끼리 이슈 처리 경험과 온라인 세션 일정을 공유합니다.</p>
      </div>

      <section className="card">
        <h2>내 도메인</h2>
        {domains.isLoading && <p className="muted">불러오는 중…</p>}
        {domains.data && open.length === 0 && <p className="muted">접근 가능한 도메인이 없습니다.</p>}
        <div className="domain-grid">
          {open.map((d) => (
            <Link key={d.vendor_id} to={`/community/${d.vendor_id}`} className="domain-card">
              <strong>{d.vendor_name}</strong>
              <span className={`badge ${d.access}`}>{ACCESS_LABELS[d.access]}</span>
              <span className="muted">
                글 {d.post_count} · 예정 세션 {d.upcoming_events}
                {d.grant_expires_at && ` · ${new Date(d.grant_expires_at).toLocaleDateString()}까지`}
              </span>
            </Link>
          ))}
        </div>
      </section>

      {closed.length > 0 && (
        <section className="card">
          <h2>다른 도메인 열람 신청</h2>
          <p className="muted">다른 벤더 도메인은 기본적으로 볼 수 없습니다. 관리자가 승인하면 정해진 기간 동안 읽기만 할 수 있습니다.</p>
          <div className="table-wrap">
            <table>
              <tbody>
                {closed.map((d) => <RequestRow key={d.vendor_id} domain={d} />)}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {mine.data && mine.data.length > 0 && (
        <section className="card">
          <h2>내 열람 신청 기록</h2>
          <div className="table-wrap">
            <table>
              <thead><tr><th>도메인</th><th>신청일</th><th>사유</th><th>상태</th><th>처리</th></tr></thead>
              <tbody>
                {mine.data.map((g) => (
                  <tr key={g.id}>
                    <td>{g.vendor_name}</td>
                    <td>{new Date(g.created_at).toLocaleDateString()}</td>
                    <td>{g.reason}</td>
                    <td>
                      <span className={`badge ${g.active ? "approved" : g.status}`}>
                        {g.status === "approved" && !g.active ? (g.grant_type === "member" ? "소속 해제됨" : "기간 만료") : GRANT_STATUS[g.status]}
                      </span>
                      {g.grant_type && <span className="muted"> {g.grant_type === "member" ? "정식 소속" : "읽기 전용"}</span>}
                    </td>
                    <td className="muted">
                      {g.decided_by_name && `${g.decided_by_name} · `}
                      {g.expires_at && g.status === "approved" && `${new Date(g.expires_at).toLocaleDateString()}까지 `}
                      {g.decision_note}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}

function RequestRow({ domain }: { domain: Domain }) {
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [days, setDays] = useState(30);
  const request = useMutation({
    mutationFn: () => api(`/community/${domain.vendor_id}/access-requests`, { method: "POST", json: { reason, days } }),
    onSuccess: () => {
      setReason("");
      queryClient.invalidateQueries({ queryKey: ["community-domains"] });
      queryClient.invalidateQueries({ queryKey: ["my-access-requests"] });
    },
  });

  return (
    <tr>
      <td style={{ width: "25%" }}><strong>{domain.vendor_name}</strong></td>
      {domain.pending_request ? (
        <td colSpan={3}><span className="badge pending">승인 대기 중</span></td>
      ) : (
        <>
          <td><input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="열람 사유 (예: 공동 고객사 장애 분석)" /></td>
          <td style={{ width: 110 }}>
            <select value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[7, 30, 90].map((n) => <option key={n} value={n}>{n}일</option>)}
            </select>
          </td>
          <td style={{ width: 90 }}>
            <button disabled={!reason.trim() || request.isPending} onClick={() => request.mutate()}>신청</button>
            {request.error && <div className="error">{request.error.message}</div>}
          </td>
        </>
      )}
    </tr>
  );
}
