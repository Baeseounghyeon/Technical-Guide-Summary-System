import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import { STATUS_LABELS } from "../labels";
import type { DocumentSummary } from "../types";

const IN_PROGRESS = new Set(["uploaded", "parsing"]);

export default function DocumentsPage() {
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const docs = useQuery({
    queryKey: ["documents"],
    queryFn: () => api<DocumentSummary[]>("/documents"),
    refetchInterval: (q) => (q.state.data?.some((d) => IN_PROGRESS.has(d.status)) ? 2000 : false),
  });

  const [vendorId, setVendorId] = useState<number | "">("");
  const [mode, setMode] = useState<"file" | "url">("file");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");

  const upload = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("vendor_id", String(vendorId));
      if (title) form.append("title", title);
      if (mode === "file" && file) form.append("file", file);
      if (mode === "url") form.append("url", url);
      return api<DocumentSummary>("/documents", { method: "POST", body: form });
    },
    onSuccess: () => {
      setFile(null);
      setUrl("");
      setTitle("");
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    upload.mutate();
  }

  const vendors = me?.vendors ?? [];

  return (
    <>
      <div className="page-header">
        <h1>벤더 기술 문서</h1>
        <p className="muted">문서를 올리면 목차를 분석합니다. 목차를 확인한 뒤 요약을 시작하세요.</p>
      </div>

      <section className="card">
        <h2>문서 가져오기</h2>
        {vendors.length === 0 ? (
          <p className="muted">접근 가능한 벤더 도메인이 없습니다. 관리자에게 도메인 지정을 요청하세요.</p>
        ) : (
          <form className="form" onSubmit={submit}>
            <div className="form-row">
              <label>
                벤더 도메인
                <select value={vendorId} onChange={(e) => setVendorId(Number(e.target.value) || "")} required>
                  <option value="">선택</option>
                  {vendors.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
                </select>
              </label>
              <label>
                제목 (선택)
                <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="비우면 문서 속 제목 또는 파일명 사용" />
              </label>
            </div>
            <div className="actions">
              <label className="check"><input type="radio" checked={mode === "file"} onChange={() => setMode("file")} />파일 (PDF, Word, PowerPoint)</label>
              <label className="check"><input type="radio" checked={mode === "url"} onChange={() => setMode("url")} />웹 문서 URL</label>
            </div>
            {mode === "file" ? (
              <input type="file" accept=".pdf,.docx,.pptx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
            ) : (
              <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://" required />
            )}
            {upload.error && <p className="error">{upload.error.message}</p>}
            <div><button className="primary" disabled={upload.isPending}>올리기</button></div>
          </form>
        )}
      </section>

      <section className="card">
        <h2>문서 목록</h2>
        {docs.isLoading ? <p className="muted">불러오는 중…</p> : docs.data?.length === 0 ? (
          <p className="muted">아직 올린 문서가 없습니다.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>제목</th><th>벤더</th><th>형식</th><th>분량</th><th>상태</th><th>등록일</th></tr></thead>
              <tbody>
                {docs.data?.map((d) => (
                  <tr key={d.id}>
                    <td><Link to={`/documents/${d.id}`}>{d.title ?? d.url ?? `문서 ${d.id}`}</Link></td>
                    <td>{d.vendor_name}</td>
                    <td>{d.source_type.toUpperCase()}</td>
                    <td>{d.page_count ? `${d.page_count}쪽` : "-"}</td>
                    <td><span className={`badge ${d.status}`}>{STATUS_LABELS[d.status]}</span></td>
                    <td>{new Date(d.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
