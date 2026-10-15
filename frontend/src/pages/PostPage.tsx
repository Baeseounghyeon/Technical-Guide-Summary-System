import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import { POST_STATUS } from "../labels";
import type { PostDetail } from "../types";

export default function PostPage() {
  const id = Number(useParams().id);
  const { me } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const key = ["post", id];
  const post = useQuery({ queryKey: key, queryFn: () => api<PostDetail>(`/community/posts/${id}`) });
  const [comment, setComment] = useState("");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({ title: "", body: "", product: "", version: "", tags: "" });

  const update = (data: PostDetail) => queryClient.setQueryData(key, data);
  const addComment = useMutation({
    mutationFn: () => api<PostDetail>(`/community/posts/${id}/comments`, { method: "POST", json: { body: comment } }),
    onSuccess: (data) => {
      setComment("");
      update(data);
    },
  });
  const setStatus = useMutation({
    mutationFn: (body: { status: "open" | "resolved"; solution_comment_id?: number }) =>
      api<PostDetail>(`/community/posts/${id}/status`, { method: "PATCH", json: body }),
    onSuccess: update,
  });
  const save = useMutation({
    mutationFn: () =>
      api<PostDetail>(`/community/posts/${id}`, {
        method: "PUT",
        json: { ...draft, tags: draft.tags.split(/[,\s]+/).filter(Boolean) },
      }),
    onSuccess: (data) => {
      setEditing(false);
      update(data);
    },
  });
  const removePost = useMutation({
    mutationFn: () => api(`/community/posts/${id}`, { method: "DELETE" }),
    onSuccess: () => navigate(`/community/${post.data?.vendor_id}`),
  });
  const removeComment = useMutation({
    mutationFn: (commentId: number) => api(`/community/comments/${commentId}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });

  if (post.isLoading) return <p className="muted">불러오는 중…</p>;
  if (post.error || !post.data) return <p className="error">{post.error?.message ?? "글을 찾을 수 없습니다."}</p>;
  const p = post.data;
  const error = addComment.error ?? setStatus.error ?? save.error ?? removePost.error ?? removeComment.error;

  function startEdit() {
    setDraft({ title: p.title, body: p.body, product: p.product ?? "", version: p.version ?? "", tags: p.tags.join(", ") });
    setEditing(true);
  }

  return (
    <>
      <div className="page-header">
        <p className="muted"><Link to="/community">커뮤니티</Link> / <Link to={`/community/${p.vendor_id}`}>도메인으로</Link></p>
        <h1>{p.title}</h1>
        <p className="muted">
          <span className={`badge ${p.status === "resolved" ? "approved" : ""}`}>{POST_STATUS[p.status]}</span>{" "}
          {[p.product, p.version].filter(Boolean).join(" ")} · {p.author.name} ({p.author.partner_name ?? "-"}) ·{" "}
          {new Date(p.created_at).toLocaleString()}
        </p>
      </div>

      <section className="card">
        {editing ? (
          <div className="form">
            <label>제목<input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></label>
            <div className="form-row">
              <label>제품<input value={draft.product} onChange={(e) => setDraft({ ...draft, product: e.target.value })} /></label>
              <label>버전<input value={draft.version} onChange={(e) => setDraft({ ...draft, version: e.target.value })} /></label>
              <label>태그<input value={draft.tags} onChange={(e) => setDraft({ ...draft, tags: e.target.value })} /></label>
            </div>
            <label>내용<textarea value={draft.body} onChange={(e) => setDraft({ ...draft, body: e.target.value })} /></label>
            <div className="actions">
              <button className="primary" disabled={save.isPending} onClick={() => save.mutate()}>저장</button>
              <button onClick={() => setEditing(false)}>취소</button>
            </div>
          </div>
        ) : (
          <>
            <div className="summary-body">{p.body}</div>
            {p.tags.length > 0 && <p className="muted">{p.tags.map((t) => `#${t}`).join(" ")}</p>}
            {p.can_edit && (
              <div className="actions" style={{ marginTop: 12 }}>
                {p.status === "open" ? (
                  <button className="ok" onClick={() => setStatus.mutate({ status: "resolved" })}>해결됨으로 표시</button>
                ) : (
                  <button onClick={() => setStatus.mutate({ status: "open" })}>다시 열기</button>
                )}
                <button onClick={startEdit}>수정</button>
                <button onClick={() => window.confirm("글을 삭제할까요?") && removePost.mutate()}>삭제</button>
              </div>
            )}
          </>
        )}
      </section>

      <section className="card">
        <h2>댓글 {p.comments.length}</h2>
        {p.comments.map((c) => (
          <div key={c.id} className={`comment ${p.solution_comment_id === c.id ? "solution" : ""}`}>
            <div className="muted">
              {c.author.name} ({c.author.partner_name ?? "-"}) · {new Date(c.created_at).toLocaleString()}
              {p.solution_comment_id === c.id && <span className="badge approved" style={{ marginLeft: 8 }}>해결 방법</span>}
            </div>
            <div className="summary-body">{c.body}</div>
            <div className="actions">
              {p.can_edit && p.solution_comment_id !== c.id && (
                <button className="link" onClick={() => setStatus.mutate({ status: "resolved", solution_comment_id: c.id })}>
                  해결 방법으로 지정
                </button>
              )}
              {(c.author.id === me?.id || me?.role === "platform_admin") && (
                <button className="link" onClick={() => removeComment.mutate(c.id)}>삭제</button>
              )}
            </div>
          </div>
        ))}
        {p.can_write ? (
          <form
            className="form"
            style={{ marginTop: 12 }}
            onSubmit={(e) => {
              e.preventDefault();
              addComment.mutate();
            }}
          >
            <textarea style={{ minHeight: 80 }} value={comment} onChange={(e) => setComment(e.target.value)} placeholder="같은 증상을 겪었거나 해결한 경험을 공유해 주세요." />
            <div><button className="primary" disabled={!comment.trim() || addComment.isPending}>댓글 등록</button></div>
          </form>
        ) : (
          <p className="muted">열람 승인된 도메인이라 댓글을 쓸 수 없습니다.</p>
        )}
        {error && <p className="error">{error.message}</p>}
      </section>
    </>
  );
}
