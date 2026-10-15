import { useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, download } from "../api";
import { useAuth } from "../auth";
import { ORIGIN_LABELS, PARTNER_GUIDE_STATUS, STATUS_LABELS, languageLabel } from "../labels";
import type { ExportItem, GuideDetail, GuideItem, Partner, PartnerGuide, Revision, RevisionInfo } from "../types";

const BUSY = new Set(["pending", "generating"]);

export default function GuidePage() {
  const id = Number(useParams().id);
  const guide = useQuery({
    queryKey: ["guide", id],
    queryFn: () => api<GuideDetail>(`/guides/${id}`),
    refetchInterval: (q) => {
      const g = q.state.data;
      const busy = g && (g.status === "queued" || g.status === "summarizing" || g.items.some((it) => it.summary && BUSY.has(it.summary.status)));
      return busy ? 2000 : false;
    },
  });

  if (guide.isLoading) return <p className="muted">불러오는 중…</p>;
  if (guide.error || !guide.data) return <p className="error">{guide.error?.message ?? "가이드를 찾을 수 없습니다."}</p>;
  const g = guide.data;
  const { total, generated, approved, failed } = g.progress;

  return (
    <>
      <div className="page-header">
        <p className="muted">
          <Link to="/">문서 목록</Link> / <Link to={`/documents/${g.document_id}`}>{g.document_title}</Link>
        </p>
        <h1>{languageLabel(g.target_language)} 요약 가이드</h1>
        <p className="muted">
          {g.vendor_name} · <span className={`badge ${g.status}`}>{STATUS_LABELS[g.status]}</span>
        </p>
      </div>

      <section className="card">
        <h2>진행 상황</h2>
        <p className="muted">
          생성 {generated}/{total} · 승인 {approved}/{total}{failed ? ` · 실패 ${failed}` : ""}
        </p>
        <div className="progress"><div style={{ width: `${total ? (generated / total) * 100 : 0}%` }} /></div>
        <div className="progress"><div style={{ width: `${total ? (approved / total) * 100 : 0}%`, background: "var(--ok)" }} /></div>
        <p className="muted">모든 항목을 승인해야 Word/PowerPoint 문서를 만들 수 있습니다.</p>
        <BulkApprove guide={g} />
      </section>

      {g.overview && (
        <section className="card">
          <h2>개요</h2>
          <div className="summary-body">{g.overview}</div>
        </section>
      )}

      {g.items.map((item) =>
        item.summary ? (
          <SummaryCard key={item.section_id} guideId={g.id} item={item} />
        ) : (
          <h3 key={item.section_id} style={{ margin: "20px 0 8px", paddingLeft: (item.level - 1) * 16 }}>{item.title}</h3>
        ),
      )}

      <ExportPanel guide={g} />
      <PartnerGuidesPanel guide={g} />
    </>
  );
}

function PartnerGuidesPanel({ guide }: { guide: GuideDetail }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const key = ["partner-guides", guide.id];
  const list = useQuery({ queryKey: key, queryFn: () => api<PartnerGuide[]>(`/guides/${guide.id}/partner-guides`) });
  const [file, setFile] = useState<File | null>(null);
  const upload = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("file", file!);
      return api<PartnerGuide>(`/guides/${guide.id}/partner-guides`, { method: "POST", body: form });
    },
    onSuccess: (pg) => {
      queryClient.invalidateQueries({ queryKey: key });
      navigate(`/partner-guides/${pg.id}`);
    },
  });
  const ready = guide.status === "approved";

  return (
    <section className="card">
      <h2>파트너 가이드 비교</h2>
      <p className="muted">
        파트너사가 따로 만든 기술 가이드를 올리면 이 요약 가이드와 벤더 원본을 기준으로 오류를 찾습니다.
        {!ready && " 모든 항목을 승인한 뒤에 사용할 수 있습니다."}
      </p>
      <form
        className="form-row"
        onSubmit={(e) => {
          e.preventDefault();
          upload.mutate();
        }}
      >
        <label>
          파트너 가이드 파일 (PDF, Word, PowerPoint)
          <input type="file" accept=".pdf,.docx,.pptx" disabled={!ready} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        <button className="primary" disabled={!ready || !file || upload.isPending}>올리고 분석</button>
      </form>
      {upload.error && <p className="error">{upload.error.message}</p>}
      {list.data && list.data.length > 0 && (
        <ul>
          {list.data.map((pg) => (
            <li key={pg.id}>
              <Link to={`/partner-guides/${pg.id}`}>{pg.title ?? `파트너 가이드 #${pg.id}`}</Link>{" "}
              <span className={`badge ${pg.status}`}>{PARTNER_GUIDE_STATUS[pg.status]}</span>{" "}
              <span className="muted">{new Date(pg.created_at).toLocaleDateString()}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function BulkApprove({ guide }: { guide: GuideDetail }) {
  const queryClient = useQueryClient();
  const drafts = guide.items.filter((it) => it.summary?.status === "draft").length;
  const others = guide.items.filter((it) => it.summary && it.summary.status !== "draft" && it.summary.status !== "approved").length;
  const approveAll = useMutation({
    mutationFn: () => api<{ approved: number; remaining: number }>(`/guides/${guide.id}/approve-all`, { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["guide", guide.id] }),
  });

  if (drafts === 0) return null;

  function confirmAndApprove() {
    const note = others ? `\n생성 중이거나 실패한 ${others}개 항목은 제외됩니다.` : "";
    if (window.confirm(`초안 ${drafts}개 항목을 모두 승인할까요?\n아직 읽어 보지 않은 항목도 함께 승인됩니다.${note}`)) {
      approveAll.mutate();
    }
  }

  return (
    <div className="actions" style={{ alignItems: "center" }}>
      <button className="ok" disabled={approveAll.isPending} onClick={confirmAndApprove}>
        초안 {drafts}개 전체 승인
      </button>
      {others > 0 && <span className="muted">생성 중·실패 {others}개는 제외됩니다.</span>}
      {approveAll.error && <span className="error">{approveAll.error.message}</span>}
    </div>
  );
}

function SummaryCard({ guideId, item }: { guideId: number; item: GuideItem }) {
  const summary = item.summary!;
  const queryClient = useQueryClient();
  const [mode, setMode] = useState<"view" | "edit" | "regen" | "history">("view");
  const [draft, setDraft] = useState(summary.content);
  const [comment, setComment] = useState("");
  const base = `/guides/${guideId}/summaries/${summary.id}`;
  const refresh = () => {
    setMode("view");
    queryClient.invalidateQueries({ queryKey: ["guide", guideId] });
  };

  const approve = useMutation({ mutationFn: () => api(`${base}/approve`, { method: "POST" }), onSuccess: refresh });
  const save = useMutation({ mutationFn: () => api(base, { method: "PUT", json: { content: draft } }), onSuccess: refresh });
  const regenerate = useMutation({
    mutationFn: () => api(`${base}/regenerate`, { method: "POST", json: { comment } }),
    onSuccess: () => {
      setComment("");
      refresh();
    },
  });
  const history = useQuery({
    queryKey: ["revisions", summary.id, summary.version],
    queryFn: () => api<Revision[]>(`${base}/revisions`),
    enabled: mode === "history",
  });

  const busy = BUSY.has(summary.status);
  const error = approve.error ?? save.error ?? regenerate.error;
  const pages = item.page_start ? `원본 p.${item.page_start}${item.page_end && item.page_end !== item.page_start ? `–${item.page_end}` : ""}` : "";

  function submitRegen(e: FormEvent) {
    e.preventDefault();
    regenerate.mutate();
  }

  return (
    <section className={`card summary-item ${summary.status}`} style={{ marginLeft: (item.level - 1) * 16 }}>
      <div className="summary-head">
        <div>
          <h3>{item.title}</h3>
          <span className="muted">{pages}{summary.version ? ` · v${summary.version}` : ""}</span>
        </div>
        <span className={`badge ${summary.status}`}>{STATUS_LABELS[summary.status]}</span>
      </div>

      {summary.error && <p className="error">{summary.error}</p>}

      {mode === "edit" ? (
        <div className="form">
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} />
          <div className="actions">
            <button className="primary" disabled={save.isPending} onClick={() => save.mutate()}>저장</button>
            <button onClick={() => setMode("view")}>취소</button>
          </div>
        </div>
      ) : (
        <>
          {summary.content && <div className="summary-body">{summary.content}</div>}
          {summary.key_steps.length > 0 && (
            <>
              <p className="muted" style={{ marginBottom: 0 }}>핵심 절차</p>
              <ol className="steps">{summary.key_steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
            </>
          )}
          {summary.warnings.length > 0 && (
            <div className="warnings">
              <strong>주의 사항</strong>
              <ul>{summary.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
            </div>
          )}
        </>
      )}

      {mode === "regen" && (
        <form className="form" style={{ marginTop: 12 }} onSubmit={submitRegen}>
          <label>
            어떻게 고칠지 적어 주세요
            <input value={comment} onChange={(e) => setComment(e.target.value)} placeholder="예: 설치 전 사전 조건을 더 자세히" required />
          </label>
          <div className="actions">
            <button className="primary" disabled={regenerate.isPending}>재생성 요청</button>
            <button type="button" onClick={() => setMode("view")}>취소</button>
          </div>
        </form>
      )}

      {mode === "history" && (
        <ol className="revisions">
          {history.data?.map((r) => (
            <li key={r.version}>
              <strong>v{r.version}</strong> {ORIGIN_LABELS[r.origin]} · {new Date(r.created_at).toLocaleString()}
              {r.comment && <div className="muted">피드백: {r.comment}</div>}
              <div className="summary-body muted">{r.content}</div>
            </li>
          ))}
        </ol>
      )}

      {error && <p className="error">{error.message}</p>}

      {mode !== "edit" && mode !== "regen" && (
        <div className="actions" style={{ marginTop: 12 }}>
          <button className="ok" disabled={busy || summary.status !== "draft" || approve.isPending} onClick={() => approve.mutate()}>승인</button>
          <button disabled={busy} onClick={() => { setDraft(summary.content); setMode("edit"); }}>직접 수정</button>
          <button disabled={busy} onClick={() => setMode("regen")}>코멘트로 재생성</button>
          <button onClick={() => setMode(mode === "history" ? "view" : "history")}>{mode === "history" ? "이력 닫기" : "변경 이력"}</button>
        </div>
      )}
    </section>
  );
}

const ASSETS: { kind: "logo" | "docx_template" | "pptx_template"; label: string; accept: string; field: keyof Partner }[] = [
  { kind: "logo", label: "로고", accept: ".png,.jpg,.jpeg", field: "logo_path" },
  { kind: "docx_template", label: "Word 양식", accept: ".docx,.dotx", field: "docx_template_path" },
  { kind: "pptx_template", label: "PowerPoint 양식", accept: ".pptx,.potx", field: "pptx_template_path" },
];

function PartnerAssets({ partner, canManage, onUploaded }: { partner: Partner; canManage: boolean; onUploaded: () => void }) {
  const upload = useMutation({
    mutationFn: ({ kind, file }: { kind: string; file: File }) => {
      const form = new FormData();
      form.append("file", file);
      return api(`/partners/${partner.id}/assets/${kind}`, { method: "POST", body: form });
    },
    onSuccess: onUploaded,
  });

  return (
    <div className="table-wrap">
      <table>
        <tbody>
          {ASSETS.map((a) => (
            <tr key={a.kind}>
              <td style={{ width: 140 }}>{a.label}</td>
              <td>
                {partner[a.field] ? <span className="badge approved">등록됨</span> : <span className="badge">없음</span>}
              </td>
              <td>
                {canManage ? (
                  <label className="check" style={{ cursor: "pointer" }}>
                    <span className="link-like">{partner[a.field] ? "다른 파일로 교체" : "파일 올리기"}</span>
                    <input
                      type="file"
                      accept={a.accept}
                      style={{ display: "none" }}
                      disabled={upload.isPending}
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) upload.mutate({ kind: a.kind, file });
                        e.target.value = "";
                      }}
                    />
                  </label>
                ) : (
                  <span className="muted">파트너 관리자만 올릴 수 있습니다</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {upload.isPending && <p className="muted">올리는 중…</p>}
      {upload.error && <p className="error">{upload.error.message}</p>}
    </div>
  );
}

function ExportPanel({ guide }: { guide: GuideDetail }) {
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const exports = useQuery({
    queryKey: ["exports", guide.id],
    queryFn: () => api<ExportItem[]>(`/guides/${guide.id}/exports`),
    refetchInterval: (q) => (q.state.data?.some((e) => e.status === "queued") ? 2000 : false),
  });

  const [format, setFormat] = useState<"docx" | "pptx">("docx");
  const [version, setVersion] = useState("1.0");
  const [includeLogo, setIncludeLogo] = useState(false);
  const [useTemplate, setUseTemplate] = useState(false);
  const [withHistory, setWithHistory] = useState(true);
  const [revision, setRevision] = useState<RevisionInfo>({
    company: me?.partner_name ?? "",
    department: me?.department ?? "",
    engineer: me?.name ?? "",
    phone: me?.phone ?? "",
    email: me?.email ?? "",
    change_note: "",
  });

  // 로고·양식을 가져올 파트너사: 관리자는 모든 파트너사, 그 외에는 자기 파트너사만.
  const isAdmin = me?.role === "platform_admin";
  const partners = useQuery({
    queryKey: ["export-partners", isAdmin, me?.partner_id],
    queryFn: async () =>
      isAdmin ? api<Partner[]>("/admin/partners") : me?.partner_id ? [await api<Partner>(`/partners/${me.partner_id}`)] : [],
  });
  const [chosenPartner, setChosenPartner] = useState<number | "" | undefined>(undefined);
  const partnerId = chosenPartner ?? guide.partner_id ?? me?.partner_id ?? partners.data?.[0]?.id ?? "";
  const partner = partners.data?.find((p) => p.id === partnerId);
  const hasTemplate = !!(format === "docx" ? partner?.docx_template_path : partner?.pptx_template_path);
  const hasLogo = !!partner?.logo_path;

  const create = useMutation({
    mutationFn: () =>
      api<ExportItem>(`/guides/${guide.id}/exports`, {
        method: "POST",
        json: {
          format,
          partner_id: partnerId === "" ? null : partnerId,
          doc_version: version,
          include_logo: includeLogo && hasLogo,
          use_partner_template: useTemplate && hasTemplate,
          revision: withHistory ? revision : null,
        },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["exports", guide.id] }),
  });

  const ready = guide.status === "approved";
  const field = (key: keyof RevisionInfo, label: string) => (
    <label>
      {label}
      <input value={revision[key]} onChange={(e) => setRevision((r) => ({ ...r, [key]: e.target.value }))} />
    </label>
  );

  return (
    <section className="card">
      <h2>최종 문서 생성</h2>
      {!ready && <p className="muted">모든 항목을 승인하면 문서를 생성할 수 있습니다.</p>}
      <form
        className="form"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <div className="form-row">
          <label>
            형식
            <select value={format} onChange={(e) => setFormat(e.target.value as "docx" | "pptx")}>
              <option value="docx">Word (.docx)</option>
              <option value="pptx">PowerPoint (.pptx)</option>
            </select>
          </label>
          <label>문서 버전<input value={version} onChange={(e) => setVersion(e.target.value)} required /></label>
        </div>
        <div className="template-box">
          <label>
            로고·양식을 쓸 파트너사
            <select value={partnerId} onChange={(e) => setChosenPartner(Number(e.target.value) || "")} disabled={!isAdmin}>
              <option value="">(사용 안 함)</option>
              {partners.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          {partner && (
            <PartnerAssets
              partner={partner}
              canManage={isAdmin || me?.role === "partner_admin"}
              onUploaded={() => queryClient.invalidateQueries({ queryKey: ["export-partners"] })}
            />
          )}
          <div className="actions">
            <label className="check">
              <input type="checkbox" checked={useTemplate && hasTemplate} disabled={!hasTemplate} onChange={(e) => setUseTemplate(e.target.checked)} />
              파트너 양식 사용 ({format === "docx" ? "Word" : "PowerPoint"})
            </label>
            <label className="check">
              <input type="checkbox" checked={includeLogo && hasLogo} disabled={!hasLogo} onChange={(e) => setIncludeLogo(e.target.checked)} />
              표지에 로고 넣기
            </label>
          </div>
          {partner && !hasTemplate && (
            <p className="muted">이 파트너사에 {format === "docx" ? "Word" : "PowerPoint"} 양식이 없습니다. 위에서 양식 파일을 올리면 사용할 수 있습니다.</p>
          )}
          <p className="muted">
            파트너 양식을 쓰면 양식 파일 안의 기존 내용은 지우고, 머리글·바닥글 로고, 글꼴·색, 슬라이드 마스터와 크기 같은 디자인만 가져와 요약 내용을 채웁니다.
          </p>
        </div>
        <div className="actions">
          <label className="check"><input type="checkbox" checked={withHistory} onChange={(e) => setWithHistory(e.target.checked)} />문서 이력 관리 표 넣기</label>
        </div>
        {withHistory && (
          <div className="form-row">
            {field("company", "소속 회사")}
            {field("department", "소속 부서")}
            {field("engineer", "엔지니어")}
            {field("phone", "연락처")}
            {field("email", "메일")}
            {field("change_note", "변경 내용")}
          </div>
        )}
        {create.error && <p className="error">{create.error.message}</p>}
        <div><button className="primary" disabled={!ready || create.isPending}>문서 생성</button></div>
      </form>

      {exports.data && exports.data.length > 0 && (
        <div className="table-wrap" style={{ marginTop: 16 }}>
          <table>
            <thead><tr><th>형식</th><th>버전</th><th>생성일</th><th>상태</th><th /></tr></thead>
            <tbody>
              {exports.data.map((e) => (
                <tr key={e.id}>
                  <td>{e.format === "docx" ? "Word" : "PowerPoint"}</td>
                  <td>v{e.doc_version}</td>
                  <td>{new Date(e.created_at).toLocaleString()}</td>
                  <td>
                    <span className={`badge ${e.status}`}>{STATUS_LABELS[e.status]}</span>
                    {e.error && <div className="error">{e.error}</div>}
                  </td>
                  <td>{e.status === "done" && <button className="link" onClick={() => download(`/exports/${e.id}/download`)}>내려받기</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
