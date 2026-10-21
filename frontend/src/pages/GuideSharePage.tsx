import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import { productLabel } from "../ProductSelect";
import type { DocumentSummary } from "../types";
import { DocumentTable } from "./DocumentsPage";

type Org = { id: number; name: string };
type OrgUser = { id: number; name: string; email: string };
interface UserShare {
  id: number;
  document_id: number;
  document_title: string | null;
  vendor_name: string;
  product: string | null;
  product_detail: string | null;
  partner_name: string;
  user_name: string;
  user_email: string;
  shared_by_name: string | null;
  created_at: string;
}

/** 가이드 공유: '가이드 공유하기'로 가이드 → 조직 → 사용자를 골라 공유한다 (승인 없이 바로).
 *  고른 사용자만 도메인 열람 신청 없이 그 가이드를 보고 내려받는다. */
export function GuideSharePanel() {
  const { me } = useAuth();
  const canShare = me?.role === "platform_admin" || !!me?.permissions.includes("guide");
  const [tab, setTab] = useState<"mine" | "received">(canShare ? "mine" : "received");
  const [sharing, setSharing] = useState(false);
  return (
    <>
      <div className="filters">
        {canShare && <button className={tab === "mine" ? "active" : ""} onClick={() => setTab("mine")}>공유한 가이드</button>}
        <button className={tab === "received" ? "active" : ""} onClick={() => setTab("received")}>공유받은 가이드</button>
        {canShare && <button className="share-open" onClick={() => setSharing(true)}>가이드 공유하기</button>}
      </div>
      {tab === "mine" ? <MyShares /> : (
        <section className="card">
          <h2 className="section-title">공유받은 가이드</h2>
          <DocumentTable query="doc_type=guide&shared_to_me=true" showGuideKind showStatus={false} />
        </section>
      )}
      {sharing && (
        <ShareDialog
          onClose={() => setSharing(false)}
          onShared={() => {
            setSharing(false);
            setTab("mine");
          }}
        />
      )}
    </>
  );
}

/** 공유한 가이드: 공유 기록(가이드 · 조직 · 사용자) 표. 해제하면 그 사용자는 더 이상 볼 수 없다. */
function MyShares() {
  const queryClient = useQueryClient();
  const shares = useQuery({ queryKey: ["user-shares"], queryFn: () => api<UserShare[]>("/user-shares") });
  const remove = useMutation({
    mutationFn: (id: number) => api(`/user-shares/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user-shares"] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
  return (
    <section className="card">
      <h2 className="section-title">공유한 가이드</h2>
      {shares.isLoading && <p className="muted">불러오는 중…</p>}
      {shares.error && <p className="error">{shares.error.message}</p>}
      {remove.error && <p className="error">{remove.error.message}</p>}
      {shares.data?.length === 0 && <p className="muted">아직 공유한 가이드가 없습니다. 위의 '가이드 공유하기' 버튼으로 공유하세요.</p>}
      {!!shares.data?.length && (
        <div className="table-wrap">
          <table style={{ minWidth: 900 }}>
            <thead>
              <tr><th>문서 이름</th><th>벤더</th><th>제품</th><th>공유 조직</th><th>공유 사용자</th><th>공유한 사람</th><th>공유 일자</th><th>해제</th></tr>
            </thead>
            <tbody>
              {shares.data.map((s) => (
                <tr key={s.id}>
                  <td><Link to={`/documents/${s.document_id}`}>{s.document_title ?? `문서 ${s.document_id}`}</Link></td>
                  <td>{s.vendor_name}</td>
                  <td>{productLabel(s.product, s.product_detail)}</td>
                  <td>{s.partner_name}</td>
                  <td title={s.user_email}>{s.user_name}</td>
                  <td>{s.shared_by_name ?? "-"}</td>
                  <td style={{ whiteSpace: "nowrap" }}>{new Date(s.created_at).toLocaleDateString()}</td>
                  <td>
                    <button
                      className="link danger-link"
                      disabled={remove.isPending}
                      onClick={() => {
                        if (window.confirm(`${s.partner_name} ${s.user_name}님에게 공유한 '${s.document_title ?? "문서"}'를 해제할까요?`)) remove.mutate(s.id);
                      }}
                    >
                      해제
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

/** 가이드 공유 창: 가이드 → 조직(파트너) → 사용자를 차례로 고른다. 사용자 목록은 고른 조직 소속만 나온다. */
function ShareDialog({ onClose, onShared }: { onClose: () => void; onShared: () => void }) {
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const isAdmin = me?.role === "platform_admin";
  const docQuery = isAdmin ? "doc_type=guide" : `doc_type=guide&uploaded_by=${me?.id}`;
  const docs = useQuery({ queryKey: ["documents", docQuery], queryFn: () => api<DocumentSummary[]>(`/documents?${docQuery}`), enabled: !!me });
  const orgs = useQuery({ queryKey: ["organizations"], queryFn: () => api<Org[]>("/organizations") });
  const [docId, setDocId] = useState("");
  const [orgId, setOrgId] = useState("");
  const [userId, setUserId] = useState("");
  const users = useQuery({
    queryKey: ["organizations", orgId, "users"],
    queryFn: () => api<OrgUser[]>(`/organizations/${orgId}/users`),
    enabled: !!orgId,
  });
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  const share = useMutation({
    mutationFn: () =>
      api("/user-shares", { method: "POST", json: { document_id: Number(docId), partner_id: Number(orgId), user_ids: [Number(userId)] } }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["user-shares"] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      onShared();
    },
  });
  // 문서를 올린 본인에게는 공유할 필요가 없다
  const owner = docs.data?.find((d) => String(d.id) === docId)?.uploaded_by;
  const candidates = (users.data ?? []).filter((u) => u.id !== owner);

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="가이드 공유">
        <div className="summary-head">
          <h2 style={{ margin: 0 }}>가이드 공유</h2>
          <button className="link" onClick={onClose}>닫기</button>
        </div>
        <p className="muted">공유할 가이드, 조직, 사용자를 모두 고르세요.</p>
        <div className="share-form">
          <label>
            가이드
            <select value={docId} onChange={(e) => setDocId(e.target.value)}>
              <option value="">가이드를 선택하세요</option>
              {docs.data?.map((d) => (
                <option key={d.id} value={d.id}>{`${d.title ?? d.url ?? `문서 ${d.id}`} (${d.vendor_name})`}</option>
              ))}
            </select>
          </label>
          {docs.data?.length === 0 && (
            <p className="muted">내가 등록한 가이드가 없습니다. <Link to="/documents?type=guide">문서 등록</Link>에서 먼저 올리세요.</p>
          )}
          <label>
            조직
            <select
              value={orgId}
              onChange={(e) => {
                setOrgId(e.target.value);
                setUserId("");
              }}
            >
              <option value="">조직(파트너)을 선택하세요</option>
              {orgs.data?.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          </label>
          <label>
            사용자
            <select value={userId} onChange={(e) => setUserId(e.target.value)} disabled={!orgId}>
              <option value="">{orgId ? "사용자를 선택하세요" : "조직을 먼저 선택하세요"}</option>
              {candidates.map((u) => <option key={u.id} value={u.id}>{`${u.name} (${u.email})`}</option>)}
            </select>
          </label>
          {orgId && users.data && candidates.length === 0 && <p className="muted">이 조직에는 공유할 수 있는 사용자가 없습니다.</p>}
        </div>
        {share.error && <p className="error">{share.error.message}</p>}
        <div className="actions" style={{ marginTop: 14 }}>
          <button className="primary" disabled={share.isPending || !docId || !orgId || !userId} onClick={() => share.mutate()}>공유</button>
          <button onClick={onClose}>취소</button>
        </div>
      </div>
    </div>
  );
}
