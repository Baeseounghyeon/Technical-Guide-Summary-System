import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { AppNotification } from "./types";

/** 상단 알림: 읽지 않은 개수 표시, 다운로드 요청은 알림 안에서 바로 승인·거절. */
export default function NotificationBell() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const notes = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<{ unread: number; items: AppNotification[] }>("/notifications"),
    refetchInterval: 30000, // 새 요청이 오면 30초 안에 표시
  });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["notifications"] });
    queryClient.invalidateQueries({ queryKey: ["download-requests"] });
    queryClient.invalidateQueries({ queryKey: ["shared-guides"] });
  };
  const read = useMutation({ mutationFn: (id: number) => api(`/notifications/${id}/read`, { method: "POST" }), onSuccess: refresh });
  const readAll = useMutation({ mutationFn: () => api("/notifications/read-all", { method: "POST" }), onSuccess: refresh });
  const decide = useMutation({
    mutationFn: ({ requestId, approve }: { requestId: number; approve: boolean }) =>
      api(`/download-requests/${requestId}/decision`, { method: "POST", json: { approve } }),
    onSuccess: refresh,
  });

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const unread = notes.data?.unread ?? 0;

  return (
    <div className="user-menu" ref={ref}>
      <button className="icon-button" onClick={() => setOpen(!open)} aria-label={`알림 ${unread}개`} aria-haspopup="menu" aria-expanded={open}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
          <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
        </svg>
        {unread > 0 && <span className="count">{unread > 9 ? "9+" : unread}</span>}
      </button>
      {open && (
        <div className="dropdown notifications" role="menu">
          <div className="dropdown-head notif-head">
            <strong>알림</strong>
            {unread > 0 && <button className="link" onClick={() => readAll.mutate()}>모두 읽음</button>}
          </div>
          {notes.data?.items.length === 0 && <p className="muted" style={{ padding: "8px 12px" }}>알림이 없습니다.</p>}
          {notes.data?.items.map((n) => (
            <div key={n.id} className={`notif ${n.read_at ? "" : "unread"}`}>
              <button
                className="notif-main"
                onClick={() => {
                  if (!n.read_at) read.mutate(n.id);
                  setOpen(false);
                  if (n.link) navigate(n.link);
                }}
              >
                <span className="notif-title">{n.title}</span>
                {n.body && <span className="notif-body">{n.body}</span>}
                <span className="notif-time">{new Date(n.created_at).toLocaleString()}</span>
              </button>
              {n.actionable && n.related_id && (
                <div className="actions notif-actions">
                  <button className="primary" disabled={decide.isPending} onClick={() => decide.mutate({ requestId: n.related_id!, approve: true })}>승인</button>
                  <button disabled={decide.isPending} onClick={() => decide.mutate({ requestId: n.related_id!, approve: false })}>거절</button>
                </div>
              )}
            </div>
          ))}
          {decide.error && <p className="error" style={{ padding: "0 12px" }}>{decide.error.message}</p>}
        </div>
      )}
    </div>
  );
}
