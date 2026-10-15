import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, fetchBlob } from "../api";
import { useAuth } from "../auth";
import { LANGUAGES } from "../labels";
import type { GlossaryTerm, Partner, Vendor } from "../types";

type AssetKind = "logo" | "docx_template" | "pptx_template";

const ASSETS: { kind: AssetKind; label: string; accept: string; hint: string }[] = [
  { kind: "logo", label: "로고", accept: ".png,.jpg,.jpeg", hint: "PNG, JPG" },
  { kind: "docx_template", label: "Word 템플릿", accept: ".docx,.dotx", hint: ".docx, .dotx" },
  { kind: "pptx_template", label: "PPT 템플릿", accept: ".pptx,.potx", hint: ".pptx, .potx" },
];

export default function SettingsPage() {
  return (
    <>
      <div className="page-header">
        <h1>설정</h1>
        <p className="muted">파트너사 로고·템플릿과 벤더 도메인 용어집을 관리합니다.</p>
      </div>
      <PartnerAssets />
      <Glossary />
    </>
  );
}

function PartnerAssets() {
  const { me } = useAuth();
  const isPlatformAdmin = me?.role === "platform_admin";
  // 플랫폼 관리자는 파트너사를 골라서, 파트너 관리자는 자기 파트너사만 관리한다.
  const partners = useQuery({
    queryKey: ["admin", "partners"],
    queryFn: () => api<Partner[]>("/admin/partners"),
    enabled: isPlatformAdmin,
  });
  const [chosen, setChosen] = useState<number | undefined>(undefined);
  const partnerId = isPlatformAdmin ? (chosen ?? me?.partner_id ?? partners.data?.[0]?.id) : me?.partner_id;

  const partner = useQuery({
    queryKey: ["partner", partnerId],
    queryFn: () => api<Partner>(`/partners/${partnerId}`),
    enabled: partnerId != null,
  });

  return (
    <section className="card">
      <h2>파트너사 로고 · 템플릿</h2>
      <p className="muted">최종 문서를 만들 때 "파트너사 로고 넣기", "파트너사 템플릿 사용"을 선택하면 여기 등록한 파일이 쓰입니다.</p>
      {isPlatformAdmin && (
        <div className="form-row">
          <label>
            파트너사
            <select value={partnerId ?? ""} onChange={(e) => setChosen(Number(e.target.value))}>
              {partners.data?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
        </div>
      )}
      {isPlatformAdmin && partners.data?.length === 0 && <p className="muted">등록된 파트너사가 없습니다. 관리자 메뉴에서 먼저 추가하세요.</p>}
      {partner.error && <p className="error">{partner.error.message}</p>}
      {partner.data && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>항목</th><th>상태</th><th>새 파일 업로드</th></tr></thead>
            <tbody>
              {ASSETS.map((a) => <AssetRow key={a.kind} partner={partner.data} asset={a} />)}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function AssetRow({ partner, asset }: { partner: Partner; asset: (typeof ASSETS)[number] }) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const registered = !!partner[`${asset.kind}_path` as const];

  const upload = useMutation({
    mutationFn: (f: File) => {
      const form = new FormData();
      form.append("file", f);
      return api<Partner>(`/partners/${partner.id}/assets/${asset.kind}`, { method: "POST", body: form });
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(["partner", partner.id], updated);
      queryClient.invalidateQueries({ queryKey: ["admin", "partners"] });
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
    },
  });

  return (
    <tr>
      <td>
        <strong>{asset.label}</strong>
        <div className="muted">{asset.hint}</div>
      </td>
      <td>
        <span className={`badge ${registered ? "done" : ""}`}>{registered ? "등록됨" : "없음"}</span>
        {asset.kind === "logo" && partner.logo_path && <LogoPreview partnerId={partner.id} logoPath={partner.logo_path} />}
      </td>
      <td>
        <form
          className="form-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (file) upload.mutate(file);
          }}
        >
          <label>
            {registered ? "교체할 파일" : "등록할 파일"}
            <input ref={inputRef} type="file" accept={asset.accept} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </label>
          <button className="primary" disabled={!file || upload.isPending}>{upload.isPending ? "올리는 중…" : "업로드"}</button>
        </form>
        {upload.error && <div className="error">{upload.error.message}</div>}
      </td>
    </tr>
  );
}

function LogoPreview({ partnerId, logoPath }: { partnerId: number; logoPath: string }) {
  // 로고 경로가 바뀌면(새 업로드) 키가 달라져 새로 받아온다.
  const blob = useQuery({
    queryKey: ["partner", partnerId, "logo", logoPath],
    queryFn: () => fetchBlob(`/partners/${partnerId}/logo`),
  });
  const [url, setUrl] = useState<string>();
  useEffect(() => {
    if (!blob.data) return;
    const objectUrl = URL.createObjectURL(blob.data);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [blob.data]);

  if (blob.error) return <div className="muted">미리보기를 불러오지 못했습니다.</div>;
  return url ? <img className="logo-preview" src={url} alt="등록된 파트너사 로고" /> : null;
}

function Glossary() {
  const queryClient = useQueryClient();
  const vendors = useQuery({ queryKey: ["vendors"], queryFn: () => api<Vendor[]>("/vendors") });
  const [chosenVendor, setVendor] = useState<number | undefined>(undefined);
  const vendorId = chosenVendor ?? vendors.data?.[0]?.id;
  const [language, setLanguage] = useState("ko");
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");

  const terms = useQuery({
    queryKey: ["glossary", vendorId, language],
    queryFn: () => api<GlossaryTerm[]>(`/vendors/${vendorId}/glossary?target_language=${encodeURIComponent(language)}`),
    enabled: vendorId != null,
  });

  const save = useMutation({
    mutationFn: (term: { source_term: string; target_term: string }) =>
      api<GlossaryTerm>(`/vendors/${vendorId}/glossary`, { method: "PUT", json: { target_language: language, ...term } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["glossary", vendorId] }),
  });

  function add(e: FormEvent) {
    e.preventDefault();
    save.mutate(
      { source_term: source.trim(), target_term: target.trim() },
      { onSuccess: () => { setSource(""); setTarget(""); } },
    );
  }

  return (
    <section className="card">
      <h2>벤더 용어집</h2>
      <p className="muted">요약·번역할 때 원어를 지정한 번역어로 옮깁니다. 같은 벤더 도메인을 지원하는 모든 파트너사가 함께 씁니다.</p>
      {vendors.data?.length === 0 && <p className="muted">접근할 수 있는 벤더 도메인이 없습니다.</p>}
      {vendorId != null && (
        <>
          <div className="form-row">
            <label>
              벤더 도메인
              <select value={vendorId} onChange={(e) => setVendor(Number(e.target.value))}>
                {vendors.data?.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
            </label>
            <label>
              번역 언어
              <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                {LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.label}</option>)}
              </select>
            </label>
          </div>
          <form className="form-row" onSubmit={add}>
            <label>원어<input value={source} onChange={(e) => setSource(e.target.value)} maxLength={200} required /></label>
            <label>번역어<input value={target} onChange={(e) => setTarget(e.target.value)} maxLength={200} required /></label>
            <button className="primary" disabled={save.isPending}>추가</button>
          </form>
          <p className="muted">이미 있는 원어를 추가하면 번역어가 바뀝니다.</p>
          {save.error && <p className="error">{save.error.message}</p>}
          {terms.error && <p className="error">{terms.error.message}</p>}
          {terms.data?.length === 0 && <p className="muted">등록된 용어가 없습니다.</p>}
          {!!terms.data?.length && (
            <div className="table-wrap">
              <table>
                <thead><tr><th>원어</th><th>번역어</th><th /></tr></thead>
                <tbody>
                  {terms.data.map((t) => (
                    <GlossaryRow key={t.id} term={t} onSave={(target_term) => save.mutate({ source_term: t.source_term, target_term })} saving={save.isPending} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}

function GlossaryRow({ term, onSave, saving }: { term: GlossaryTerm; onSave: (target: string) => void; saving: boolean }) {
  const [draft, setDraft] = useState(term.target_term);
  useEffect(() => setDraft(term.target_term), [term.target_term]);
  const changed = draft.trim() !== "" && draft.trim() !== term.target_term;

  return (
    <tr>
      <td>{term.source_term}</td>
      <td><input value={draft} onChange={(e) => setDraft(e.target.value)} maxLength={200} aria-label={`${term.source_term} 번역어`} /></td>
      <td className="actions">
        <button disabled={!changed || saving} onClick={() => onSave(draft.trim())}>저장</button>
        {changed && <button className="link" onClick={() => setDraft(term.target_term)}>취소</button>}
      </td>
    </tr>
  );
}
