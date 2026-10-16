import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import { LANGUAGES, STATUS_LABELS, languageLabel } from "../labels";
import type { DocumentDetail, GuideBrief, Section, Usage } from "../types";

export default function DocumentPage() {
  const { me } = useAuth();
  const id = Number(useParams().id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const key = ["document", id];
  const doc = useQuery({
    queryKey: key,
    queryFn: () => api<DocumentDetail>(`/documents/${id}`),
    refetchInterval: (q) => (q.state.data && ["uploaded", "parsing"].includes(q.state.data.status) ? 2000 : false),
  });
  const [language, setLanguage] = useState("ko");
  const usage = useQuery({ queryKey: ["usage", id], queryFn: () => api<Usage>(`/usage?document_id=${id}`) });

  const toggle = useMutation({
    mutationFn: (s: Section) => api<Section>(`/sections/${s.id}`, { method: "PATCH", json: { included: !s.included } }),
    onSuccess: (updated) => {
      queryClient.setQueryData<DocumentDetail>(key, (old) =>
        old && { ...old, sections: old.sections.map((s) => (s.id === updated.id ? updated : s)) },
      );
      queryClient.invalidateQueries({ queryKey: ["usage", id] });
    },
  });

  const startGuide = useMutation({
    mutationFn: () => api<GuideBrief>(`/documents/${id}/guides`, { method: "POST", json: { target_language: language } }),
    onSuccess: (guide) => navigate(`/guides/${guide.id}`),
  });

  if (doc.isLoading) return <p className="muted">불러오는 중…</p>;
  if (doc.error || !doc.data) return <p className="error">{doc.error?.message ?? "문서를 찾을 수 없습니다."}</p>;
  const d = doc.data;
  // 요약은 가이드 권한이 있고, 내 조직 문서일 때만 (공유받음·도메인 열람은 읽기 전용)
  const canSummarize = (me?.role === "platform_admin" || !!me?.permissions.includes("guide")) && d.access === "own";
  const included = d.sections.filter((s) => s.included);
  const includedChars = included.reduce((sum, s) => sum + s.char_count, 0);
  const u = usage.data;
  const estimate = u?.estimate_pages ?? 0;
  const overQuota = !!u && !u.unlimited && estimate > u.remaining_pages;
  const blocked = !!u && (u.budget_exceeded || overQuota);

  return (
    <>
      <div className="page-header">
        <p className="muted"><Link to="/documents">문서 목록</Link> / {d.vendor_name}</p>
        <h1>{d.title ?? d.url}</h1>
        <p className="muted">
          {d.source_type.toUpperCase()} · {d.page_count ? `${d.page_count}쪽 · ` : ""}
          <span className={`badge ${d.status}`}>{STATUS_LABELS[d.status]}</span>
        </p>
        {d.error && <p className="error">{d.error}</p>}
      </div>

      {d.guides.length > 0 && (
        <section className="card">
          <h2>요약 가이드</h2>
          <ul>
            {d.guides.map((g) => (
              <li key={g.id}>
                <Link to={`/guides/${g.id}`}>{languageLabel(g.target_language)} 가이드 #{g.id}</Link>{" "}
                <span className={`badge ${g.status}`}>{STATUS_LABELS[g.status]}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {d.status === "parsed" && !canSummarize && (
        <section className="card">
          <p className="muted">
            {d.access !== "own"
              ? "다른 조직이 공유했거나 도메인 권한으로 열람하는 문서입니다. 보기와 내려받기만 할 수 있습니다."
              : "가이드 등록·요약 권한이 없어 이 문서는 내려받기만 할 수 있습니다. 필요하면 요청 > 권한 승인 요청에서 신청하세요."}
          </p>
        </section>
      )}

      {d.status === "parsed" && canSummarize && (
        <>
          <section className="card">
            <h2>요약 시작</h2>
            <p className="muted">
              목차 {d.sections.length}개 중 {included.length}개 항목, 약 {includedChars.toLocaleString()}자를 요약합니다.
              아래 목차에서 법적 고지·색인처럼 필요 없는 항목은 빼 주세요.
            </p>
            {u && (
              <p className={blocked ? "error" : "muted"}>
                AI 사용량: 이번 요약 약 <strong>{estimate.toLocaleString()}쪽</strong>
                {u.unlimited
                  ? " (관리자: 회사 한도 없음)"
                  : ` · 회사 이번 달 남은 양 ${u.remaining_pages.toLocaleString()}쪽 / 월 ${u.quota_pages.toLocaleString()}쪽`}
                {u.budget_exceeded && " · 이번 달 전체 AI 예산을 모두 사용했습니다."}
                {overQuota && " · 남은 양보다 많습니다. 요약할 목차를 줄이거나 관리자에게 한도를 요청하세요."}
              </p>
            )}
            <div className="form-row">
              <label>
                가이드 언어
                <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                  {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
                </select>
              </label>
              <button className="primary" disabled={startGuide.isPending || included.length === 0 || blocked} onClick={() => startGuide.mutate()}>
                요약 시작
              </button>
            </div>
            {startGuide.error && <p className="error">{startGuide.error.message}</p>}
          </section>

          <section className="card toc">
            <h2>목차 확인</h2>
            <ul>
              {d.sections.map((s) => (
                <li key={s.id} style={{ paddingLeft: (s.level - 1) * 20 }}>
                  <label className="check">
                    <input type="checkbox" checked={s.included} onChange={() => toggle.mutate(s)} />
                    <span className={s.included ? "" : "excluded"}>{s.title}</span>
                    <span className="muted">
                      {s.page_start ? ` p.${s.page_start}${s.page_end && s.page_end !== s.page_start ? `–${s.page_end}` : ""}` : ""}
                      {` · ${s.char_count.toLocaleString()}자`}
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </>
  );
}
