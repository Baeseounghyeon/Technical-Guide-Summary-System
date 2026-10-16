import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import type { DocumentSummary } from "../types";
import { DocumentTable } from "./DocumentsPage";

type Org = { id: number; name: string };

/** 가이드 공유: 내가 등록한 가이드를 어느 조직까지 공유할지 정한다 (여러 조직 선택).
 *  공유받은 조직은 도메인 권한 요청 없이 그 가이드를 보고 내려받을 수 있다. */
export default function GuideSharePage() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "received" ? "received" : "mine";
  return (
    <>
      <div className="page-header">
        <h1>가이드 공유</h1>
        <p className="muted">
          내가 등록한 가이드를 공유할 조직을 고릅니다(여러 개 선택 가능). 공유받은 조직은 도메인 권한 요청 없이 그 가이드를 보고 내려받을 수 있습니다.
        </p>
      </div>
      <div className="filters">
        <button className={tab === "mine" ? "active" : ""} onClick={() => setParams({})}>공유한 가이드</button>
        <button className={tab === "received" ? "active" : ""} onClick={() => setParams({ tab: "received" })}>공유받은 가이드</button>
      </div>
      {tab === "mine" ? <MySharedGuides /> : (
        <section className="card">
          <h2 className="section-title">공유받은 가이드</h2>
          <DocumentTable query="doc_type=guide&shared_to_me=true" showGuideKind showStatus={false} />
        </section>
      )}
    </>
  );
}

function MySharedGuides() {
  const { me } = useAuth();
  const [editing, setEditing] = useState<DocumentSummary | null>(null);
  const docs = useQuery({
    queryKey: ["documents", `doc_type=guide&uploaded_by=${me?.id}`],
    queryFn: () => api<DocumentSummary[]>(`/documents?doc_type=guide&uploaded_by=${me?.id}`),
    enabled: !!me,
  });
  return (
    <section className="card">
      <h2 className="section-title">공유한 가이드</h2>
      {docs.isLoading && <p className="muted">불러오는 중…</p>}
      {docs.error && <p className="error">{docs.error.message}</p>}
      {docs.data?.length === 0 && (
        <p className="muted">내가 등록한 가이드가 없습니다. <Link to="/documents?type=guide">가이드 등록</Link>에서 먼저 올리세요.</p>
      )}
      {!!docs.data?.length && (
        <div className="table-wrap">
          <table style={{ minWidth: 820 }}>
            <thead>
              <tr><th>문서 이름</th><th>벤더</th><th>등록 일자</th><th>사용자명</th><th>공유 범위</th><th>설정</th></tr>
            </thead>
            <tbody>
              {docs.data.map((d) => (
                <tr key={d.id}>
                  <td><Link to={`/documents/${d.id}`}>{d.title ?? d.url ?? `문서 ${d.id}`}</Link></td>
                  <td>{d.vendor_name}</td>
                  <td>{new Date(d.created_at).toLocaleDateString()}</td>
                  <td>{d.uploaded_by_name ?? "-"}</td>
                  <td>
                    <div className="actions">
                      <span className="badge member" title="내 조직은 항상 볼 수 있습니다">{d.partner_name ?? "내 조직"}</span>
                      {d.shared_with.map((n) => <span key={n} className="badge granted">{n}</span>)}
                    </div>
                  </td>
                  <td><button className="link" onClick={() => setEditing(d)}>공유 범위 설정</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {editing && <ShareDialog doc={editing} onClose={() => setEditing(null)} />}
    </section>
  );
}

function ShareDialog({ doc, onClose }: { doc: DocumentSummary; onClose: () => void }) {
  const queryClient = useQueryClient();
  const orgs = useQuery({ queryKey: ["organizations"], queryFn: () => api<Org[]>("/organizations") });
  const [checked, setChecked] = useState<Set<string>>(new Set(doc.shared_with));
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);
  const save = useMutation({
    mutationFn: () => {
      const ids = (orgs.data ?? []).filter((o) => checked.has(o.name)).map((o) => o.id);
      return api(`/documents/${doc.id}/shares`, { method: "PUT", json: { partner_ids: ids } });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      onClose();
    },
  });
  const toggle = (name: string) =>
    setChecked((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });

  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="공유 범위 설정">
        <div className="summary-head">
          <h2 style={{ margin: 0 }}>공유 범위 설정</h2>
          <button className="link" onClick={onClose}>닫기</button>
        </div>
        <p className="muted">{doc.title ?? doc.url}</p>
        {orgs.isLoading && <p className="muted">불러오는 중…</p>}
        <div className="share-list">
          {orgs.data?.map((o) => {
            const own = o.id === doc.partner_id;
            return (
              <label key={o.id} className="check">
                <input type="checkbox" checked={own || checked.has(o.name)} disabled={own} onChange={() => toggle(o.name)} />
                {o.name}
                {own && <span className="muted"> (내 조직 · 항상 공유)</span>}
              </label>
            );
          })}
        </div>
        {save.error && <p className="error">{save.error.message}</p>}
        <div className="actions" style={{ marginTop: 14 }}>
          <button className="primary" disabled={save.isPending || !orgs.data} onClick={() => save.mutate()}>저장</button>
          <button onClick={onClose}>취소</button>
        </div>
      </div>
    </div>
  );
}
