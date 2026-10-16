import { useState, type FormEvent, type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import { TRACK_LABELS } from "../labels";

interface PermissionRequest {
  id: number;
  user_id: number;
  user_track: string | null;
  scopes: string[];
  scope_labels: string[];
  reason: string;
  name: string | null;
  email: string | null;
  company: string | null;
  phone: string | null;
  status: "pending" | "approved" | "rejected" | "revoked";
  decided_by_name: string | null;
  decided_at: string | null;
  decision_note: string | null;
  created_at: string;
}

/** 신청할 수 있는 권한 범위 (브로슈어는 모두 기본으로 가짐) */
const SCOPES = [
  { key: "guide", label: "가이드 등록·요약", detail: "가이드 문서 등록, 요약 요청·검토, 최종 문서(Word·PPT) 생성, 가이드 공유" },
  { key: "spec", label: "규격서 등록", detail: "규격서 문서 등록·수정" },
  { key: "quote", label: "견적서 등록·생성", detail: "견적서 참고 자료·양식 등록, 견적서 생성" },
];
const STATUS_LABELS: Record<string, string> = { pending: "승인 대기", approved: "승인", rejected: "반려", revoked: "회수" };
const STATUS_BADGE: Record<string, string> = { pending: "pending", approved: "done", rejected: "failed", revoked: "failed" };

/** 권한 승인 요청: 내 업무 구분 밖의 권한(예: 영업이 가이드 등록·요약)을 관리자에게 신청한다. */
export function PermissionRequestPage() {
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const mine = useQuery({ queryKey: ["permission-requests", "mine"], queryFn: () => api<PermissionRequest[]>("/permission-requests/mine") });
  const [scopes, setScopes] = useState<Set<string>>(new Set());
  const [form, setForm] = useState({
    name: me?.name ?? "",
    company: me?.partner_name ?? me?.company_name ?? "",
    email: me?.email ?? "",
    phone: me?.phone ?? "",
    reason: "",
  });
  const send = useMutation({
    mutationFn: () => api("/permission-requests", { method: "POST", json: { ...form, scopes: [...scopes] } }),
    onSuccess: () => {
      setScopes(new Set());
      setForm((f) => ({ ...f, reason: "" }));
      queryClient.invalidateQueries({ queryKey: ["permission-requests"] });
    },
  });
  if (me?.role === "platform_admin") return <Navigate to="/admin#permission-requests" replace />;

  const have = new Set(me?.permissions ?? []);
  const pending = mine.data?.some((r) => r.status === "pending");
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const toggle = (key: string) =>
    setScopes((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    send.mutate();
  };

  return (
    <>
      <div className="page-header">
        <h1>권한 승인 요청</h1>
        <p className="muted">
          지금 업무 구분({TRACK_LABELS[me?.track ?? "engineer"]})에 없는 권한을 관리자에게 신청합니다. 예를 들어 영업 담당이 엔지니어의 가이드 등록·요약을
          함께 하려면 '가이드 등록·요약'을 신청하세요.
        </p>
      </div>
      <section className="card">
        <form className="form" onSubmit={submit}>
          <div>
            <strong>신청할 권한 범위</strong>
            <div className="scope-list">
              {SCOPES.map((s) => {
                const owned = have.has(s.key);
                return (
                  <label key={s.key} className={`scope-option${owned ? " owned" : ""}`}>
                    <input type="checkbox" checked={owned || scopes.has(s.key)} disabled={owned} onChange={() => toggle(s.key)} />
                    <span>
                      <strong>{s.label}</strong>
                      {owned && <span className="badge done" style={{ marginLeft: 6 }}>보유</span>}
                      <span className="muted" style={{ display: "block" }}>{s.detail}</span>
                    </span>
                  </label>
                );
              })}
            </div>
          </div>
          <div>
            <strong>신청자 정보</strong>
            <p className="muted" style={{ margin: "2px 0 6px" }}>가입할 때 입력한 정보입니다. 바뀐 내용이 있으면 고쳐서 보내세요.</p>
            <div className="form-row">
              <label>성명<input value={form.name} onChange={set("name")} required /></label>
              <label>회사명<input value={form.company} onChange={set("company")} /></label>
              <label>이메일<input type="email" value={form.email} onChange={set("email")} required /></label>
              <label>전화번호<input value={form.phone} onChange={set("phone")} /></label>
            </div>
          </div>
          <label>
            내용 (신청 사유)
            <textarea value={form.reason} onChange={set("reason")} rows={4} required placeholder="예: 고객사 기술 지원을 겸하게 되어 가이드 등록·요약이 필요합니다." />
          </label>
          {pending && <p className="muted">승인 대기 중인 요청이 있어 처리된 뒤에 다시 신청할 수 있습니다.</p>}
          {send.error && <p className="error">{send.error.message}</p>}
          <div>
            <button className="primary" disabled={send.isPending || scopes.size === 0 || pending}>{send.isPending ? "보내는 중…" : "권한 승인 요청 보내기"}</button>
          </div>
        </form>
      </section>
      <section className="card">
        <h2 className="section-title">내 권한 요청</h2>
        <RequestTable rows={mine.data} loading={mine.isLoading} showRequester={false} />
      </section>
    </>
  );
}

/** 관리자: 권한 승인 요청 승인·반려 (승인한 것은 회수 가능). */
export function AdminPermissionRequests() {
  const queryClient = useQueryClient();
  const [showAll, setShowAll] = useState(false);
  const rows = useQuery({
    queryKey: ["admin", "permission-requests", showAll],
    queryFn: () => api<PermissionRequest[]>(`/admin/permission-requests${showAll ? "" : "?status=pending"}`),
  });
  const [notes, setNotes] = useState<Record<number, string>>({});
  const decide = useMutation({
    mutationFn: ({ id, approve }: { id: number; approve: boolean }) =>
      api(`/admin/permission-requests/${id}/decision`, { method: "POST", json: { approve, note: notes[id] ?? "" } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin"] }),
  });
  const pendingCount = rows.data?.filter((r) => r.status === "pending").length ?? 0;
  return (
    <section className="card" id="permission-requests" style={{ scrollMarginTop: 80 }}>
      <div className="summary-head">
        <h2 style={{ margin: 0 }}>권한 승인 요청 처리</h2>
        {pendingCount > 0 && <span className="badge pending">대기 {pendingCount}건</span>}
      </div>
      <label className="check" style={{ margin: "8px 0" }}>
        <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
        처리한 요청도 보기
      </label>
      {decide.error && <p className="error">{decide.error.message}</p>}
      <RequestTable
        rows={rows.data}
        loading={rows.isLoading}
        showRequester
        actions={(r) =>
          r.status === "pending" || r.status === "approved" ? (
            <div className="form" style={{ gap: 6 }}>
              <input
                placeholder="메모 (선택)"
                value={notes[r.id] ?? ""}
                onChange={(e) => setNotes((n) => ({ ...n, [r.id]: e.target.value }))}
              />
              <div className="actions">
                {r.status === "pending" && (
                  <button className="primary" disabled={decide.isPending} onClick={() => decide.mutate({ id: r.id, approve: true })}>승인</button>
                )}
                <button disabled={decide.isPending} onClick={() => decide.mutate({ id: r.id, approve: false })}>
                  {r.status === "pending" ? "반려" : "권한 회수"}
                </button>
              </div>
            </div>
          ) : null
        }
      />
    </section>
  );
}

function RequestTable({
  rows, loading, showRequester, actions,
}: {
  rows: PermissionRequest[] | undefined;
  loading: boolean;
  showRequester: boolean;
  actions?: (r: PermissionRequest) => ReactNode;
}) {
  if (loading) return <p className="muted">불러오는 중…</p>;
  if (!rows?.length) return <p className="muted">권한 요청이 없습니다.</p>;
  return (
    <div className="table-wrap">
      <table style={{ minWidth: 860 }}>
        <thead>
          <tr>
            {showRequester && <th>신청자</th>}
            <th>신청 범위</th><th>내용</th><th>신청일</th><th>결과</th><th>관리자 메모</th>
            {actions && <th>처리</th>}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id}>
              {showRequester && (
                <td>
                  <strong>{r.name}</strong> <span className="muted">({TRACK_LABELS[r.user_track ?? "engineer"]})</span>
                  <div className="muted">{[r.company, r.email, r.phone].filter(Boolean).join(" · ")}</div>
                </td>
              )}
              <td>{r.scope_labels.join(", ")}</td>
              <td style={{ maxWidth: 280 }}>{r.reason}</td>
              <td style={{ whiteSpace: "nowrap" }}>{new Date(r.created_at).toLocaleDateString()}</td>
              <td>
                <span className={`badge ${STATUS_BADGE[r.status]}`}>{STATUS_LABELS[r.status]}</span>
                {r.decided_by_name && <div className="muted">{r.decided_by_name}</div>}
              </td>
              <td>{r.decision_note ?? <span className="muted">-</span>}</td>
              {actions && <td style={{ minWidth: 200 }}>{actions(r)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
