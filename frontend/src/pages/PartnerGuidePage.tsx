import { useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, download } from "../api";
import {
  FINDING_CATEGORY,
  FINDING_STATUS,
  LOG_ACTION,
  PARTNER_GUIDE_STATUS,
  SEVERITY_LABELS,
  STATUS_LABELS,
} from "../labels";
import type { CorrectionExport, CorrectionLog, Finding, FindingStatus, PartnerGuideDetail, PartnerSection } from "../types";

const BUSY = new Set(["uploaded", "parsing", "comparing"]);

export default function PartnerGuidePage() {
  const id = Number(useParams().id);
  const queryClient = useQueryClient();
  const key = ["partner-guide", id];
  const detail = useQuery({
    queryKey: key,
    queryFn: () => api<PartnerGuideDetail>(`/partner-guides/${id}`),
    refetchInterval: (q) => (q.state.data && BUSY.has(q.state.data.status) ? 2000 : false),
  });
  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: key });
    queryClient.invalidateQueries({ queryKey: ["partner-history", id] });
  };
  const compare = useMutation({ mutationFn: () => api(`/partner-guides/${id}/compare`, { method: "POST" }), onSuccess: refresh });

  if (detail.isLoading) return <p className="muted">불러오는 중…</p>;
  if (detail.error || !detail.data) return <p className="error">{detail.error?.message ?? "파트너 가이드를 찾을 수 없습니다."}</p>;
  const pg = detail.data;
  const busy = BUSY.has(pg.status);
  const matchedCount = pg.sections.filter((s) => s.matched_section_id).length;

  return (
    <>
      <div className="page-header">
        <p className="muted">
          <Link to="/">문서 목록</Link> / <Link to={`/guides/${pg.guide_id}`}>{pg.vendor_document_title} 요약 가이드</Link>
        </p>
        <h1>{pg.title ?? "파트너 가이드"}</h1>
        <p className="muted">
          {pg.source_type.toUpperCase()} · 기준: {pg.vendor_name} 원본 ·{" "}
          <span className={`badge ${pg.status}`}>{PARTNER_GUIDE_STATUS[pg.status]}</span>
        </p>
        {pg.error && <p className="error" style={{ whiteSpace: "pre-wrap" }}>{pg.error}</p>}
      </div>

      {pg.status === "comparing" && (
        <section className="card">
          <h2>비교 중</h2>
          <p className="muted">{pg.progress_current}/{pg.progress_total} 항목 완료</p>
          <div className="progress"><div style={{ width: `${pg.progress_total ? (pg.progress_current / pg.progress_total) * 100 : 0}%` }} /></div>
        </section>
      )}

      {!["uploaded", "parsing", "failed"].includes(pg.status) && (
        <MatchingCard
          pg={pg}
          disabled={busy}
          onChanged={refresh}
          action={
            <button className="primary" disabled={busy || matchedCount === 0 || compare.isPending} onClick={() => compare.mutate()}>
              {pg.status === "reviewing" ? "다시 비교" : "비교 시작"}
            </button>
          }
          error={compare.error?.message}
        />
      )}

      {pg.findings.length > 0 && <FindingsCard pg={pg} onChanged={refresh} />}
      {pg.status === "reviewing" && pg.findings.length === 0 && (
        <section className="card"><p>벤더 원본과 다른 오류 후보를 찾지 못했습니다.</p></section>
      )}
      {pg.findings.length > 0 && <ExportsCard pg={pg} />}
      {pg.findings.length > 0 && <HistoryCard id={pg.id} />}
    </>
  );
}

function MatchingCard({
  pg, disabled, onChanged, action, error,
}: { pg: PartnerGuideDetail; disabled: boolean; onChanged: () => void; action: ReactNode; error?: string }) {
  const patch = useMutation({
    mutationFn: ({ section, vendorId }: { section: PartnerSection; vendorId: number | null }) =>
      api(`/partner-sections/${section.id}`, { method: "PATCH", json: { matched_section_id: vendorId } }),
    onSuccess: onChanged,
  });
  const matched = pg.sections.filter((s) => s.matched_section_id).length;

  return (
    <section className="card">
      <h2>목차 매칭 확인</h2>
      <p className="muted">
        파트너 가이드 목차 {pg.sections.length}개 중 {matched}개가 벤더 원본과 연결되었습니다. 틀린 연결은 고친 뒤 비교를 시작하세요.
        연결되지 않은 항목은 비교하지 않습니다.
      </p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>파트너 가이드 목차</th><th>벤더 원본 목차</th><th>연결</th></tr></thead>
          <tbody>
            {pg.sections.map((s) => (
              <tr key={s.id}>
                <td style={{ paddingLeft: 8 + (s.level - 1) * 16 }}>
                  {s.title} <span className="muted">· {s.char_count.toLocaleString()}자</span>
                </td>
                <td>
                  <select
                    value={s.matched_section_id ?? ""}
                    disabled={disabled || patch.isPending}
                    onChange={(e) => patch.mutate({ section: s, vendorId: e.target.value ? Number(e.target.value) : null })}
                  >
                    <option value="">(대응 없음)</option>
                    {pg.vendor_sections.map((v) => (
                      <option key={v.id} value={v.id}>{" ".repeat((v.level - 1) * 2)}{v.title}</option>
                    ))}
                  </select>
                </td>
                <td className="muted">{s.match_method === "manual" ? "수동" : s.match_method === "auto" ? "자동" : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(error || patch.error) && <p className="error">{error ?? patch.error?.message}</p>}
      <div style={{ marginTop: 12 }}>{action}</div>
    </section>
  );
}

function FindingsCard({ pg, onChanged }: { pg: PartnerGuideDetail; onChanged: () => void }) {
  const [filter, setFilter] = useState<FindingStatus | "all">("open");
  const { total, open, accepted, rejected } = pg.counts;
  const shown = pg.findings.filter((f) => filter === "all" || f.status === filter);
  const tabs: [FindingStatus | "all", string][] = [["open", `미결정 ${open}`], ["accepted", `수락 ${accepted}`], ["rejected", `거절 ${rejected}`], ["all", `전체 ${total}`]];

  return (
    <section className="card">
      <h2>오류 후보</h2>
      <p className="muted">판단 근거는 벤더 원본입니다. 수락한 항목만 수정본에 반영되고, 모든 결정은 이력으로 남습니다.</p>
      <div className="filters">
        {tabs.map(([value, label]) => (
          <button key={value} className={filter === value ? "active" : ""} onClick={() => setFilter(value)}>{label}</button>
        ))}
      </div>
      {shown.length === 0 && <p className="muted">해당하는 항목이 없습니다.</p>}
      {shown.map((f) => <FindingCard key={f.id} finding={f} onChanged={onChanged} />)}
    </section>
  );
}

function FindingCard({ finding: f, onChanged }: { finding: Finding; onChanged: () => void }) {
  const [mode, setMode] = useState<"view" | "edit" | "reject">("view");
  const [text, setText] = useState(f.after_text);
  const [note, setNote] = useState("");
  const decide = useMutation({
    mutationFn: (body: { action: string; final_text?: string; note?: string }) =>
      api(`/findings/${f.id}/decision`, { method: "POST", json: body }),
    onSuccess: () => {
      setMode("view");
      setNote("");
      onChanged();
    },
  });
  const applied = f.status === "accepted" ? (f.final_text ?? f.after_text) : f.after_text;

  return (
    <div className={`card finding ${f.status}`}>
      <div className="summary-head">
        <div>
          <h3>{f.partner_section_title}</h3>
          <span className="muted">
            원본: {f.vendor_section_title ?? "-"}{f.vendor_page_start ? ` (p.${f.vendor_page_start})` : ""}
          </span>
        </div>
        <div className="actions">
          <span className="badge">{FINDING_CATEGORY[f.category] ?? f.category}</span>
          <span className={`badge ${f.severity}`}>{SEVERITY_LABELS[f.severity]}</span>
          <span className={`badge ${f.status}`}>{FINDING_STATUS[f.status]}</span>
        </div>
      </div>

      <div className="diff">
        <div className="before"><b>수정 전</b><span>{f.before_text}</span></div>
        <div className="after"><b>{f.status === "accepted" && f.final_text !== f.after_text ? "수정 후 (직접 고침)" : "수정 후"}</b>{applied}</div>
      </div>
      <p style={{ margin: "4px 0" }}><strong>사유</strong> {f.reason}</p>
      {f.evidence && <div className="evidence">벤더 원본: {f.evidence}</div>}
      {!f.locatable && <p className="error">파트너 원문에서 '수정 전' 문구를 그대로 찾지 못해, 수정본에는 자동 반영되지 않습니다.</p>}

      {f.status !== "open" && (
        <p className="muted">
          {FINDING_STATUS[f.status]} · {f.decided_by_name}{f.decided_at ? ` · ${new Date(f.decided_at).toLocaleString()}` : ""}
          {f.decision_note ? ` · 메모: ${f.decision_note}` : ""}
        </p>
      )}

      {mode === "edit" && (
        <div className="form">
          <label>반영할 문구<textarea style={{ minHeight: 80 }} value={text} onChange={(e) => setText(e.target.value)} /></label>
          <label>메모 (선택)<input value={note} onChange={(e) => setNote(e.target.value)} /></label>
          <div className="actions">
            <button className="primary" disabled={decide.isPending} onClick={() => decide.mutate({ action: "accept", final_text: text, note })}>고친 문구로 수락</button>
            <button onClick={() => setMode("view")}>취소</button>
          </div>
        </div>
      )}
      {mode === "reject" && (
        <div className="form">
          <label>거절 사유 (필수)<input value={note} onChange={(e) => setNote(e.target.value)} placeholder="예: 파트너 환경에서는 수동 모드 사용" /></label>
          <div className="actions">
            <button className="primary" disabled={!note.trim() || decide.isPending} onClick={() => decide.mutate({ action: "reject", note })}>거절</button>
            <button onClick={() => setMode("view")}>취소</button>
          </div>
        </div>
      )}
      {decide.error && <p className="error">{decide.error.message}</p>}

      {mode === "view" && (
        <div className="actions" style={{ marginTop: 8 }}>
          {f.status === "open" ? (
            <>
              <button className="ok" disabled={decide.isPending} onClick={() => decide.mutate({ action: "accept" })}>수락</button>
              <button onClick={() => { setText(f.after_text); setMode("edit"); }}>고쳐서 수락</button>
              <button onClick={() => setMode("reject")}>거절</button>
            </>
          ) : (
            <button disabled={decide.isPending} onClick={() => decide.mutate({ action: "reopen" })}>되돌리기</button>
          )}
        </div>
      )}
    </div>
  );
}

function ExportsCard({ pg }: { pg: PartnerGuideDetail }) {
  const queryClient = useQueryClient();
  const key = ["correction-exports", pg.id];
  const exports = useQuery({
    queryKey: key,
    queryFn: () => api<CorrectionExport[]>(`/partner-guides/${pg.id}/exports`),
    refetchInterval: (q) => (q.state.data?.some((e) => e.status === "queued") ? 2000 : false),
  });
  const create = useMutation({
    mutationFn: (kind: "tracked" | "report") => api(`/partner-guides/${pg.id}/exports`, { method: "POST", json: { kind } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: key }),
  });
  const canTrack = pg.source_type === "docx" && pg.counts.accepted > 0;

  return (
    <section className="card">
      <h2>수정본 · 보고서</h2>
      <p className="muted">
        수정본은 Word의 "변경 내용 추적"으로 수락한 항목을 표시합니다 (Word 파트너 가이드만 가능). 보고서는 모든 후보의 수정 전·후, 사유, 근거, 결정을 담습니다.
        {pg.counts.open > 0 && ` 아직 미결정 ${pg.counts.open}건이 있습니다.`}
      </p>
      <div className="actions">
        <button className="primary" disabled={!canTrack || create.isPending} onClick={() => create.mutate("tracked")}>변경 추적 수정본 만들기</button>
        <button disabled={create.isPending} onClick={() => create.mutate("report")}>수정 보고서 만들기</button>
      </div>
      {create.error && <p className="error">{create.error.message}</p>}
      {exports.data && exports.data.length > 0 && (
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table>
            <thead><tr><th>종류</th><th>생성일</th><th>상태</th><th /></tr></thead>
            <tbody>
              {exports.data.map((e) => (
                <tr key={e.id}>
                  <td>
                    {e.kind === "tracked" ? "변경 추적 수정본" : "수정 보고서"}
                    {e.kind === "tracked" && e.status === "done" && (
                      <div className="muted">반영 {e.applied_count}건{e.skipped_count ? ` · 위치를 못 찾아 제외 ${e.skipped_count}건` : ""}</div>
                    )}
                  </td>
                  <td>{new Date(e.created_at).toLocaleString()}</td>
                  <td><span className={`badge ${e.status}`}>{STATUS_LABELS[e.status]}</span>{e.error && <div className="error">{e.error}</div>}</td>
                  <td>{e.status === "done" && <button className="link" onClick={() => download(`/correction-exports/${e.id}/download`)}>내려받기</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function HistoryCard({ id }: { id: number }) {
  const [open, setOpen] = useState(false);
  const history = useQuery({
    queryKey: ["partner-history", id],
    queryFn: () => api<CorrectionLog[]>(`/partner-guides/${id}/history`),
    enabled: open,
  });

  return (
    <section className="card">
      <div className="summary-head">
        <h2 style={{ margin: 0 }}>수정 이력</h2>
        <button onClick={() => setOpen(!open)}>{open ? "닫기" : "보기"}</button>
      </div>
      {open && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>일시</th><th>담당</th><th>결정</th><th>수정 전</th><th>수정 후</th><th>사유 · 메모</th></tr></thead>
            <tbody>
              {history.data?.map((h) => (
                <tr key={h.id}>
                  <td>{new Date(h.created_at).toLocaleString()}</td>
                  <td style={{ whiteSpace: "nowrap" }}>{h.user_name}</td>
                  <td style={{ whiteSpace: "nowrap" }}>{LOG_ACTION[h.action]}</td>
                  <td>{h.before_text}</td>
                  <td>{h.after_text ?? "-"}</td>
                  <td>{h.reason}{h.note && <div className="muted">메모: {h.note}</div>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {history.data?.length === 0 && <p className="muted">아직 결정한 항목이 없습니다.</p>}
        </div>
      )}
    </section>
  );
}
