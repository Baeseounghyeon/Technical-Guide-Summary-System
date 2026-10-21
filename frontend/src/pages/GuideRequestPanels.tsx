import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, download } from "../api";
import { useAuth } from "../auth";
import { languageLabel } from "../labels";
import type { DownloadRequest, SharedExport, SharedGuide } from "../types";

const REQUEST_STATUS: Record<string, { label: string; badge: string }> = {
  none: { label: "요청 전", badge: "" },
  pending: { label: "승인 대기", badge: "pending" },
  approved: { label: "승인됨", badge: "approved" },
  rejected: { label: "거절됨", badge: "failed" },
};

/** 가이드 받기: 같은 벤더의 다른 파트너사가 만든 가이드를 골라 다운로드를 요청한다. */
export function SharedGuidesPanel() {
  const { me } = useAuth();
  const guides = useQuery({ queryKey: ["shared-guides"], queryFn: () => api<SharedGuide[]>("/shared-guides") });

  if (!me?.partner_id) {
    return <section className="card"><p className="muted">소속 파트너사가 있는 계정만 다른 파트너사의 가이드를 요청할 수 있습니다.</p></section>;
  }
  return (
    <section className="card">
      <h2 className="section-title">다른 파트너사 가이드</h2>
      {guides.isLoading && <p className="muted">불러오는 중…</p>}
      {guides.data?.length === 0 && <p className="muted">같은 벤더 도메인에서 다른 파트너사가 최종 문서까지 만든 가이드가 아직 없습니다.</p>}
      {!!guides.data?.length && (
        <div className="table-wrap">
          <table style={{ minWidth: 900 }}>
            <thead>
              <tr><th>문서</th><th>벤더</th><th>파트너사</th><th>언어</th><th>형식</th><th>최근 생성</th><th>상태</th><th /></tr>
            </thead>
            <tbody>
              {guides.data.map((g) => <SharedGuideRow key={g.guide_id} guide={g} />)}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function SharedGuideRow({ guide: g }: { guide: SharedGuide }) {
  const queryClient = useQueryClient();
  const [asking, setAsking] = useState(false);
  const [message, setMessage] = useState("");
  const status = REQUEST_STATUS[g.request_status];
  const request = useMutation({
    mutationFn: () => api(`/shared-guides/${g.guide_id}/requests`, { method: "POST", json: { message } }),
    onSuccess: () => {
      setAsking(false);
      setMessage("");
      queryClient.invalidateQueries({ queryKey: ["shared-guides"] });
      queryClient.invalidateQueries({ queryKey: ["download-requests"] });
    },
  });
  const exports = useQuery({
    queryKey: ["shared-exports", g.guide_id],
    queryFn: () => api<SharedExport[]>(`/shared-guides/${g.guide_id}/exports`),
    enabled: g.request_status === "approved",
  });

  return (
    <>
      <tr>
        <td style={{ minWidth: 220 }}><strong>{g.title}</strong></td>
        <td>{g.vendor_name}</td>
        <td>{g.owner_partner_name}</td>
        <td style={{ whiteSpace: "nowrap" }}>{languageLabel(g.target_language)}</td>
        <td style={{ whiteSpace: "nowrap" }}>{g.formats.map((f) => (f === "docx" ? "Word" : "PowerPoint")).join(", ")}</td>
        <td style={{ whiteSpace: "nowrap" }}>{new Date(g.updated_at).toLocaleDateString()}</td>
        <td>
          <span className={`badge ${status.badge}`}>{status.label}</span>
          {g.decision_note && <div className="muted">{g.decision_note}</div>}
        </td>
        <td style={{ whiteSpace: "nowrap" }}>
          {g.request_status === "approved" ? (
            <div className="actions">
              {exports.data?.map((e) => (
                <button key={e.id} className="link" onClick={() => download(`/exports/${e.id}/download`)}>
                  {e.format === "docx" ? "Word" : "PPT"} v{e.doc_version} 받기
                </button>
              ))}
            </div>
          ) : (g.request_status === "none" || g.request_status === "rejected") && !asking ? (
            <button className="primary" onClick={() => setAsking(true)}>{g.request_status === "rejected" ? "다시 요청" : "다운로드 요청"}</button>
          ) : null}
        </td>
      </tr>
      {asking && (
        <tr>
          <td colSpan={8}>
            <div className="form-row">
              <label>요청 사유 (소유 파트너사에 전달됩니다)<input value={message} onChange={(e) => setMessage(e.target.value)} placeholder="예: 공동 고객사 설치 지원" /></label>
              <div className="actions">
                <button className="primary" disabled={request.isPending} onClick={() => request.mutate()}>요청 보내기</button>
                <button onClick={() => setAsking(false)}>취소</button>
              </div>
            </div>
            {request.error && <p className="error">{request.error.message}</p>}
          </td>
        </tr>
      )}
    </>
  );
}

/** 가이드 받기 요청 표. incoming: 우리 가이드에 들어온 요청(승인 처리), outgoing: 우리 파트너사가 보낸 요청. */
export function DownloadRequestsPanel({ kind }: { kind: "incoming" | "outgoing" }) {
  const requests = useQuery({
    queryKey: ["download-requests", kind],
    queryFn: () => api<DownloadRequest[]>(`/download-requests/${kind}`),
  });

  return (
    <section className="card">
      <h2 style={{ margin: "0 0 4px" }}>{kind === "incoming" ? "가이드 받기" : "우리 파트너사가 보낸 요청"}</h2>
      {kind === "incoming" && <p className="muted">다른 파트너사가 우리 가이드를 받겠다고 보낸 요청입니다. 파트너 관리자와 그 문서를 올린 사람이 승인합니다.</p>}
      {requests.data?.length === 0 && <p className="muted">요청이 없습니다.</p>}
      {!!requests.data?.length && (
        <div className="table-wrap">
          <table style={{ minWidth: 860 }}>
            <thead>
              <tr>
                <th>{kind === "incoming" ? "요청자" : "요청한 사람"}</th><th>문서</th><th>{kind === "incoming" ? "요청 파트너사" : "소유 파트너사"}</th>
                <th>요청 사유</th><th>요청일</th><th>상태</th><th />
              </tr>
            </thead>
            <tbody>
              {requests.data.map((r) => <RequestRow key={r.id} req={r} kind={kind} />)}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function RequestRow({ req: r, kind }: { req: DownloadRequest; kind: "incoming" | "outgoing" }) {
  const queryClient = useQueryClient();
  const [note, setNote] = useState("");
  const decide = useMutation({
    mutationFn: (approve: boolean) => api(`/download-requests/${r.id}/decision`, { method: "POST", json: { approve, note } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["download-requests"] });
      queryClient.invalidateQueries({ queryKey: ["approvals"] });
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
  const status = REQUEST_STATUS[r.status];

  return (
    <tr>
      <td style={{ whiteSpace: "nowrap" }}>{r.requester_name}<div className="muted">{r.requester_email}</div></td>
      <td style={{ minWidth: 180 }}>{r.guide_title}<div className="muted">{r.vendor_name}</div></td>
      <td>{kind === "incoming" ? r.requester_partner_name : r.owner_partner_name}</td>
      <td>{r.message ?? <span className="muted">-</span>}</td>
      <td style={{ whiteSpace: "nowrap" }}>{new Date(r.created_at).toLocaleDateString()}</td>
      <td>
        <span className={`badge ${status.badge}`}>{status.label}</span>
        {r.decided_by_name && <div className="muted">{r.decided_by_name}{r.decision_note ? ` · ${r.decision_note}` : ""}</div>}
      </td>
      <td style={{ minWidth: 220 }}>
        {r.can_decide && (
          <div className="form">
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="메모 (선택)" />
            <div className="actions">
              <button className="primary" disabled={decide.isPending} onClick={() => decide.mutate(true)}>승인</button>
              <button disabled={decide.isPending} onClick={() => decide.mutate(false)}>거절</button>
            </div>
            {decide.error && <span className="error">{decide.error.message}</span>}
          </div>
        )}
      </td>
    </tr>
  );
}
