import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { ACCESS_LABELS, POST_STATUS } from "../labels";
import type { Domain, PostDetail, PostSummary, SessionEvent } from "../types";

export default function DomainPage() {
  const vendorId = Number(useParams().vendorId);
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "events" ? "events" : "posts";
  const domains = useQuery({ queryKey: ["community-domains"], queryFn: () => api<Domain[]>("/community/domains") });
  const domain = domains.data?.find((d) => d.vendor_id === vendorId);

  if (domains.isLoading) return <p className="muted">불러오는 중…</p>;
  if (!domain || domain.access === "none") {
    return (
      <section className="card">
        <p className="error">이 도메인 커뮤니티를 볼 권한이 없습니다.</p>
        <Link to="/community">커뮤니티에서 열람 신청하기</Link>
      </section>
    );
  }
  const canWrite = domain.access === "member";

  return (
    <>
      <div className="page-header">
        <p className="muted"><Link to="/community">커뮤니티</Link></p>
        <h1>{domain.vendor_name}</h1>
        <p className="muted">
          <span className={`badge ${domain.access}`}>{ACCESS_LABELS[domain.access]}</span>
          {domain.grant_expires_at && ` ${new Date(domain.grant_expires_at).toLocaleDateString()}까지 열람할 수 있습니다.`}
        </p>
      </div>
      <div className="filters">
        <button className={tab === "posts" ? "active" : ""} onClick={() => setParams({})}>이슈 공유</button>
        <button className={tab === "events" ? "active" : ""} onClick={() => setParams({ tab: "events" })}>온라인 세션</button>
      </div>
      {tab === "posts" ? <PostsTab vendorId={vendorId} canWrite={canWrite} /> : <EventsTab vendorId={vendorId} canWrite={canWrite} />}
    </>
  );
}

function PostsTab({ vendorId, canWrite }: { vendorId: number; canWrite: boolean }) {
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [tag, setTag] = useState("");
  const [writing, setWriting] = useState(false);
  const query = new URLSearchParams(Object.entries({ q: search, status, tag }).filter(([, v]) => v));
  const posts = useQuery({
    queryKey: ["posts", vendorId, search, status, tag],
    queryFn: () => api<PostSummary[]>(`/community/${vendorId}/posts?${query}`),
  });

  return (
    <>
      {writing && <PostForm vendorId={vendorId} onClose={() => setWriting(false)} />}
      <section className="card">
        <form
          className="form-row"
          onSubmit={(e) => {
            e.preventDefault();
            setSearch(q.trim());
          }}
        >
          <label>검색 (제목·본문·제품·버전)<input value={q} onChange={(e) => setQ(e.target.value)} /></label>
          <label style={{ flex: "0 0 140px" }}>
            상태
            <select value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">전체</option>
              <option value="open">해결 중</option>
              <option value="resolved">해결됨</option>
            </select>
          </label>
          <button>검색</button>
          {canWrite && !writing && <button type="button" className="primary" onClick={() => setWriting(true)}>새 글</button>}
        </form>
        {tag && (
          <p className="muted">
            태그 #{tag} 로 거른 결과 · <button className="link" onClick={() => setTag("")}>태그 해제</button>
          </p>
        )}
        {!canWrite && <p className="muted">열람 승인된 도메인이라 글과 댓글은 쓸 수 없습니다.</p>}

        {posts.data?.length === 0 && <p className="muted">글이 없습니다.</p>}
        <ul className="post-list">
          {posts.data?.map((p) => (
            <li key={p.id}>
              <div>
                <Link to={`/community/posts/${p.id}`}><strong>{p.title}</strong></Link>{" "}
                <span className={`badge ${p.status === "resolved" ? "approved" : ""}`}>{POST_STATUS[p.status]}</span>
              </div>
              <div className="muted">
                {[p.product, p.version].filter(Boolean).join(" ")}
                {(p.product || p.version) && " · "}
                {p.author.name} ({p.author.partner_name ?? "-"}) · {new Date(p.created_at).toLocaleDateString()} · 댓글 {p.comment_count}
              </div>
              {p.tags.length > 0 && (
                <div className="actions" style={{ marginTop: 4 }}>
                  {p.tags.map((t) => <button key={t} className="link" onClick={() => setTag(t)}>#{t}</button>)}
                </div>
              )}
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

function PostForm({ vendorId, onClose }: { vendorId: number; onClose: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ title: "", body: "", product: "", version: "", tags: "" });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const create = useMutation({
    mutationFn: () =>
      api<PostDetail>(`/community/${vendorId}/posts`, {
        method: "POST",
        json: { ...form, tags: form.tags.split(/[,\s]+/).filter(Boolean) },
      }),
    onSuccess: (post) => {
      queryClient.invalidateQueries({ queryKey: ["posts", vendorId] });
      queryClient.invalidateQueries({ queryKey: ["community-domains"] });
      navigate(`/community/posts/${post.id}`);
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    create.mutate();
  }

  return (
    <section className="card">
      <h2>이슈 공유하기</h2>
      <form className="form" onSubmit={submit}>
        <label>제목<input value={form.title} onChange={set("title")} required placeholder="예: 4.3 업그레이드 후 VPN 터널 끊김" /></label>
        <div className="form-row">
          <label>제품<input value={form.product} onChange={set("product")} /></label>
          <label>버전<input value={form.version} onChange={set("version")} /></label>
          <label>태그 (쉼표·공백 구분)<input value={form.tags} onChange={set("tags")} placeholder="vpn, upgrade" /></label>
        </div>
        <label>내용 (증상, 원인, 조치)<textarea value={form.body} onChange={set("body")} required /></label>
        {create.error && <p className="error">{create.error.message}</p>}
        <div className="actions">
          <button className="primary" disabled={create.isPending}>등록</button>
          <button type="button" onClick={onClose}>취소</button>
        </div>
      </form>
    </section>
  );
}

function EventsTab({ vendorId, canWrite }: { vendorId: number; canWrite: boolean }) {
  const queryClient = useQueryClient();
  const [scope, setScope] = useState<"upcoming" | "past">("upcoming");
  const key = ["events", vendorId, scope];
  const events = useQuery({ queryKey: key, queryFn: () => api<SessionEvent[]>(`/community/${vendorId}/events?scope=${scope}`) });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["events", vendorId] });
    queryClient.invalidateQueries({ queryKey: ["community-domains"] });
  };
  const rsvp = useMutation({
    mutationFn: (e: SessionEvent) => api(`/community/events/${e.id}/rsvp?attending=${!e.attending}`, { method: "POST" }),
    onSuccess: refresh,
  });
  const remove = useMutation({ mutationFn: (id: number) => api(`/community/events/${id}`, { method: "DELETE" }), onSuccess: refresh });

  return (
    <>
      {canWrite && <EventForm vendorId={vendorId} onCreated={refresh} />}
      <section className="card">
        <div className="filters">
          <button className={scope === "upcoming" ? "active" : ""} onClick={() => setScope("upcoming")}>예정</button>
          <button className={scope === "past" ? "active" : ""} onClick={() => setScope("past")}>지난 세션</button>
        </div>
        {events.data?.length === 0 && <p className="muted">일정이 없습니다.</p>}
        {events.data?.map((e) => (
          <div key={e.id} className="event">
            <div className="summary-head">
              <div>
                <h3>{e.title}</h3>
                <span className="muted">
                  {new Date(e.starts_at).toLocaleString()}
                  {e.ends_at && ` ~ ${new Date(e.ends_at).toLocaleTimeString()}`} · {e.organizer.name} ({e.organizer.partner_name ?? "-"})
                </span>
              </div>
              <span className="badge">참석 {e.attendee_count}</span>
            </div>
            {e.description && <p className="summary-body">{e.description}</p>}
            {e.attendees.length > 0 && <p className="muted">참석: {e.attendees.join(", ")}</p>}
            <div className="actions">
              {scope === "upcoming" && (
                <button className={e.attending ? "" : "ok"} disabled={rsvp.isPending} onClick={() => rsvp.mutate(e)}>
                  {e.attending ? "참석 취소" : "참석"}
                </button>
              )}
              {e.join_url && <a href={e.join_url} target="_blank" rel="noreferrer">접속 링크</a>}
              {e.can_edit && <button className="link" onClick={() => remove.mutate(e.id)}>삭제</button>}
            </div>
          </div>
        ))}
      </section>
    </>
  );
}

function EventForm({ vendorId, onCreated }: { vendorId: number; onCreated: () => void }) {
  const empty = { title: "", description: "", starts_at: "", ends_at: "", join_url: "" };
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(empty);
  const set = (key: keyof typeof empty) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const create = useMutation({
    mutationFn: () =>
      api(`/community/${vendorId}/events`, {
        method: "POST",
        json: {
          ...form,
          // 입력한 현지 시각을 UTC 로 바꿔 보낸다.
          starts_at: new Date(form.starts_at).toISOString(),
          ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
        },
      }),
    onSuccess: () => {
      setForm(empty);
      setOpen(false);
      onCreated();
    },
  });

  if (!open) {
    return <div style={{ marginBottom: 16 }}><button className="primary" onClick={() => setOpen(true)}>세션 일정 등록</button></div>;
  }
  return (
    <section className="card">
      <h2>세션 일정 등록</h2>
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <label>제목<input value={form.title} onChange={set("title")} required /></label>
        <div className="form-row">
          <label>시작<input type="datetime-local" value={form.starts_at} onChange={set("starts_at")} required /></label>
          <label>종료<input type="datetime-local" value={form.ends_at} onChange={set("ends_at")} /></label>
        </div>
        <label>접속 링크<input type="url" value={form.join_url} onChange={set("join_url")} placeholder="https://" /></label>
        <label>설명<textarea style={{ minHeight: 80 }} value={form.description} onChange={set("description")} /></label>
        {create.error && <p className="error">{create.error.message}</p>}
        <div className="actions">
          <button className="primary" disabled={create.isPending}>등록</button>
          <button type="button" onClick={() => setOpen(false)}>취소</button>
        </div>
      </form>
    </section>
  );
}
