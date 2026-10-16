import { Fragment, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import { GRANT_STATUS, ROLE_LABELS, TRACK_LABELS } from "../labels";
import { AdminPermissionRequests } from "./PermissionPages";
import type { AccessGrant, AdminUser, Partner, PartnerUsage, Role, Track, UsageOverview, Vendor } from "../types";

export default function AdminPage() {
  return (
    <>
      <div className="page-header">
        <h1>관리자</h1>
        <p className="muted">가입자 승인·수정·삭제, AI 사용량과 회사별 한도, 다른 도메인 권한 신청, 파트너사와 벤더 도메인을 관리합니다.</p>
      </div>
      <Members />
      <AdminPermissionRequests />
      <AiUsage />
      <AccessRequests />
      <PartnersAndVendors />
    </>
  );
}

function Members() {
  const [track, setTrack] = useState<Track>("engineer");
  const [statusFilter, setStatusFilter] = useState("");
  const [q, setQ] = useState("");
  const users = useQuery({
    queryKey: ["admin", "users", "all", statusFilter],
    queryFn: () => api<AdminUser[]>(`/admin/users${statusFilter ? `?status=${statusFilter}` : ""}`),
  });
  const partners = useQuery({ queryKey: ["admin", "partners"], queryFn: () => api<Partner[]>("/admin/partners") });
  const [editing, setEditing] = useState<number | null>(null);
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const remove = useMutation({
    mutationFn: (id: number) => api(`/admin/users/${id}`, { method: "DELETE" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin"] }),
  });
  const keyword = q.trim().toLowerCase();
  const trackOf = (u: AdminUser): Track => u.track ?? "engineer";
  const counts = { engineer: 0, sales: 0 };
  for (const u of users.data ?? []) counts[trackOf(u)] += 1;
  // 승인 대기자를 맨 위로
  const shown = (users.data ?? [])
    .filter((u) => trackOf(u) === track)
    .filter((u) => !keyword || [u.name, u.email, u.partner_name, u.company_name].some((v) => v?.toLowerCase().includes(keyword)))
    .sort((a, b) => Number(b.status === "pending") - Number(a.status === "pending"));
  const pendingCount = (users.data ?? []).filter((u) => u.status === "pending").length;
  const pendingIn = (t: Track) => (users.data ?? []).filter((u) => u.status === "pending" && trackOf(u) === t).length;

  return (
    <section className="card">
      <div className="summary-head">
        <h2 style={{ margin: 0 }}>가입자</h2>
        {pendingCount > 0 && <span className="badge pending">승인 대기 {pendingCount}명</span>}
      </div>
      <div className="filters">
        {(["engineer", "sales"] as Track[]).map((t) => (
          <button key={t} className={track === t ? "active" : ""} onClick={() => setTrack(t)}>
            {TRACK_LABELS[t]} {counts[t]}명{pendingIn(t) ? ` · 대기 ${pendingIn(t)}` : ""}
          </button>
        ))}
      </div>
      <div className="form-row" style={{ marginBottom: 8 }}>
        <label>검색 (이름·메일·회사)<input value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <label style={{ flex: "0 0 160px" }}>
          상태
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="">전체</option>
            <option value="active">사용 중</option>
            <option value="pending">승인 대기</option>
            <option value="suspended">정지</option>
          </select>
        </label>
      </div>
      <p className="muted">{shown.length}명</p>
      {remove.error && <p className="error">{remove.error.message}</p>}
      <div className="table-wrap">
        <table style={{ minWidth: 900 }}>
          <thead>
            <tr><th>소속</th><th>이름</th><th>이메일</th><th>전화번호</th><th>도메인</th><th>상태</th><th /></tr>
          </thead>
          <tbody>
            {shown.map((u) => (
              <Fragment key={u.id}>
              <tr className={u.status === "pending" ? "highlight" : ""}>
                <td style={{ minWidth: 120 }}>
                  {u.partner_name ?? <span className="muted">미지정</span>}
                  {(u.department || (!u.partner_name && u.company_name)) && (
                    <div className="muted">{[u.department, !u.partner_name && u.company_name ? `신청: ${u.company_name}` : null].filter(Boolean).join(" · ")}</div>
                  )}
                </td>
                <td style={{ whiteSpace: "nowrap" }} title={`가입: ${new Date(u.created_at).toLocaleString()}`}>{u.name}</td>
                <td>{u.email}</td>
                <td style={{ whiteSpace: "nowrap" }}>{u.phone || "-"}</td>
                <td>
                  {u.role === "platform_admin" ? (
                    <span className="muted">전체 도메인</span>
                  ) : u.domains.length === 0 && u.read_grants.length === 0 ? (
                    <span className="muted">없음</span>
                  ) : (
                    <div className="actions">
                      {u.domains.map((d) => <span key={d} className="badge member">{d}</span>)}
                      {u.read_grants.map((g) => (
                        <span key={g.vendor_name} className="badge granted" title="기간 한정 읽기 전용">
                          {g.vendor_name} 읽기 ~{new Date(g.expires_at).toLocaleDateString()}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
                <td><span className={`badge ${u.status}`}>{USER_STATUS[u.status]}</span></td>
                <td style={{ whiteSpace: "nowrap" }}>
                  {editing !== u.id && (
                    <div className="actions">
                      <button className={u.status === "pending" ? "primary" : "link"} onClick={() => setEditing(u.id)}>
                        {u.status === "pending" ? "승인하기" : "수정"}
                      </button>
                      {u.id !== me?.id && (
                        <button
                          className="link danger-link"
                          disabled={remove.isPending}
                          onClick={() => {
                            if (window.confirm(`${u.name}(${u.email}) 가입자를 삭제할까요?\n삭제하면 로그인할 수 없고 목록에서 사라집니다. 올린 문서와 작성 기록은 남습니다.`)) {
                              remove.mutate(u.id);
                            }
                          }}
                        >
                          삭제
                        </button>
                      )}
                    </div>
                  )}
                </td>
              </tr>
              {editing === u.id && (
                <tr className={u.status === "pending" ? "highlight" : ""}>
                  <td colSpan={7}>
                    <AssignForm user={u} partners={partners.data ?? []} onDone={() => setEditing(null)} />
                  </td>
                </tr>
              )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const USER_STATUS: Record<string, string> = { active: "사용 중", pending: "승인 대기", suspended: "정지" };

function AccessRequests() {
  const queryClient = useQueryClient();
  const [showAll, setShowAll] = useState(false);
  const requests = useQuery({
    queryKey: ["admin", "access-requests", showAll],
    queryFn: () => api<AccessGrant[]>(`/admin/access-requests${showAll ? "" : "?status=pending"}`),
  });
  // 정식 소속 승인·회수는 파트너사-도메인 표도 바꾸므로 관리자 화면 전체를 새로 고친다.
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin"] });
  const revoke = useMutation({ mutationFn: (id: number) => api(`/admin/access-requests/${id}/revoke`, { method: "POST" }), onSuccess: refresh });

  return (
    <section className="card" id="access-requests" style={{ scrollMarginTop: 80 }}>
      <div className="summary-head">
        <h2 style={{ margin: 0 }}>도메인 권한 요청 승인</h2>
        <label className="check"><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />처리한 신청도 보기</label>
      </div>
      <p className="muted">
        승인 방식을 고를 수 있습니다. 읽기 전용은 신청자만 정한 기간 동안 커뮤니티를 볼 수 있고, 정식 소속은 신청자의 파트너사 전체에 그 벤더 도메인을 부여합니다. 둘 다 회수할 수 있습니다.
      </p>
      {requests.data?.length === 0 && <p className="muted">{showAll ? "신청 기록이 없습니다." : "대기 중인 신청이 없습니다."}</p>}
      <div className="table-wrap">
        <table>
          <tbody>
            {requests.data?.map((g) =>
              g.status === "pending" ? (
                <AccessRequestRow key={g.id} grant={g} onDone={refresh} />
              ) : (
                <tr key={g.id}>
                  <td>
                    <strong>{g.user.name}</strong> <span className="muted">{g.user.partner_name} → {g.vendor_name}</span>
                    <div className="muted">요청 목적: {g.reason}{g.request_date ? ` · 요청 일자 ${g.request_date}` : ""}</div>
                  </td>
                  <td>
                    <span className={`badge ${g.active ? "approved" : g.status}`}>
                      {g.status === "approved" && !g.active ? (g.grant_type === "member" ? "소속 해제됨" : "기간 만료") : GRANT_STATUS[g.status]}
                    </span>
                    {g.grant_type && <span className="muted"> {g.grant_type === "member" ? "정식 소속" : "읽기 전용"}</span>}
                    <div className="muted">
                      {g.decided_by_name}
                      {g.expires_at && g.status === "approved" && ` · ${new Date(g.expires_at).toLocaleDateString()}까지`}
                      {g.decision_note && ` · ${g.decision_note}`}
                    </div>
                  </td>
                  <td>{g.active && <button onClick={() => revoke.mutate(g.id)}>회수</button>}</td>
                </tr>
              ),
            )}
          </tbody>
        </table>
      </div>
      {revoke.error && <p className="error">{revoke.error.message}</p>}
    </section>
  );
}

function AccessRequestRow({ grant, onDone }: { grant: AccessGrant; onDone: () => void }) {
  const [grantType, setGrantType] = useState<"read" | "member">("read");
  const [days, setDays] = useState(grant.requested_days);
  const [note, setNote] = useState("");
  const decide = useMutation({
    mutationFn: (approve: boolean) =>
      api(`/admin/access-requests/${grant.id}/decision`, { method: "POST", json: { approve, grant_type: grantType, days, note } }),
    onSuccess: onDone,
  });

  return (
    <tr>
      <td>
        <strong>{grant.requester_name ?? grant.user.name}</strong> <span className="muted">{grant.requester_email ?? grant.user_email}</span>
        <div className="muted">
          {grant.requester_company ?? grant.user.partner_name} → <strong>{grant.vendor_name}</strong> · 신청 {new Date(grant.created_at).toLocaleDateString()}
          {grant.request_date && ` · 요청 일자 ${grant.request_date}`}
        </div>
        <div>요청 목적: {grant.reason}</div>
        {decide.error && <div className="error">{decide.error.message}</div>}
      </td>
      <td style={{ width: 260 }}>
        <label className="check">
          <input type="radio" checked={grantType === "read"} onChange={() => setGrantType("read")} />
          기간 한정 읽기 전용 (신청자만)
        </label>
        {grantType === "read" && (
          <label style={{ marginLeft: 22 }}>
            기간(일)
            <input type="number" min={1} max={365} value={days} onChange={(e) => setDays(Number(e.target.value))} />
          </label>
        )}
        <label className="check">
          <input type="radio" checked={grantType === "member"} onChange={() => setGrantType("member")} />
          정식 소속 부여
        </label>
        {grantType === "member" && (
          <div className="muted" style={{ marginLeft: 22 }}>
            {grant.user.partner_name ?? "신청자 파트너사"} 전체가 {grant.vendor_name} 도메인에서 읽기·쓰기·문서 업로드를 할 수 있습니다. 기간 제한 없음.
          </div>
        )}
      </td>
      <td><label>메모<input value={note} onChange={(e) => setNote(e.target.value)} /></label></td>
      <td style={{ whiteSpace: "nowrap" }}>
        <button className="primary" disabled={decide.isPending} onClick={() => decide.mutate(true)}>승인</button>{" "}
        <button disabled={decide.isPending} onClick={() => decide.mutate(false)}>거절</button>
      </td>
    </tr>
  );
}

const PERMISSION_LABELS: Record<string, string> = { guide: "가이드", spec: "규격서", quote: "견적서", brochure: "브로슈어" };

/** 가입 승인 또는 수정: 가입자 정보(성명·회사명·이메일·전화번호·부서), 소속·권한·업무 구분, 사용자별 도메인을 한 번에 저장한다. */
function AssignForm({ user, partners, onDone }: { user: AdminUser; partners: Partner[]; onDone: () => void }) {
  const queryClient = useQueryClient();
  const vendors = useQuery({ queryKey: ["vendors"], queryFn: () => api<Vendor[]>("/vendors") });
  // 고르기 전에는 현재 소속 → 신청 회사명과 같은 파트너사 순으로 제안한다 (목록이 늦게 와도 반영되도록 매번 계산).
  const [chosen, setPartnerId] = useState<number | "" | undefined>(undefined);
  const partnerId = chosen ?? user.partner_id ?? partners.find((p) => p.name === user.company_name)?.id ?? "";
  const [role, setRole] = useState<Role>(user.status === "pending" ? "engineer" : user.role);
  const [track, setTrack] = useState<Track>(user.track ?? "engineer");
  const [profile, setProfile] = useState({
    name: user.name,
    company_name: user.company_name ?? "",
    email: user.email,
    phone: user.phone ?? "",
    department: user.department ?? "",
  });
  // 도메인: 기본은 소속 파트너사의 도메인, 체크를 끄면 사용자별로 체크한 것만
  const [useDefault, setUseDefault] = useState(!user.custom_domains);
  const [domainIds, setDomainIds] = useState<Set<number>>(new Set(user.domain_ids));
  const partnerVendorIds = new Set(partners.find((p) => p.id === partnerId)?.vendors.map((v) => v.id) ?? []);
  const isAdminRole = role === "platform_admin";

  const save = useMutation({
    mutationFn: async () => {
      await api(`/admin/users/${user.id}/profile`, { method: "PUT", json: profile });
      await api(`/admin/users/${user.id}/approve`, {
        method: "POST",
        json: { partner_id: partnerId === "" ? null : partnerId, role, track },
      });
      if (!isAdminRole) {
        await api(`/admin/users/${user.id}/domains`, {
          method: "PUT",
          json: useDefault ? { use_partner_default: true } : { vendor_ids: [...domainIds] },
        });
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin"] });
      onDone();
    },
  });
  const pending = user.status === "pending";
  const set = (key: keyof typeof profile) => (e: { target: { value: string } }) => setProfile((p) => ({ ...p, [key]: e.target.value }));
  const toggleDomain = (id: number) =>
    setDomainIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  return (
    <div className="user-edit">
      <div className="user-edit-block">
        <strong>가입자 정보</strong>
        <div className="form-row">
          <label>성명<input value={profile.name} onChange={set("name")} required /></label>
          <label>회사명<input value={profile.company_name} onChange={set("company_name")} /></label>
          <label>이메일<input type="email" value={profile.email} onChange={set("email")} required /></label>
          <label>전화번호<input value={profile.phone} onChange={set("phone")} /></label>
          <label>부서<input value={profile.department} onChange={set("department")} /></label>
        </div>
      </div>
      <div className="user-edit-block">
        <strong>소속 · 권한</strong>
        <div className="form-row">
          <label>
            소속 파트너사
            <select value={partnerId} onChange={(e) => setPartnerId(Number(e.target.value) || "")}>
              <option value="">{isAdminRole ? "(없음)" : "파트너사 선택"}</option>
              {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <label style={{ flex: "0 0 180px" }}>
            권한
            <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
              {Object.entries(ROLE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
          <label style={{ flex: "0 0 140px" }}>
            업무 구분
            <select value={track} onChange={(e) => setTrack(e.target.value as Track)}>
              {Object.entries(TRACK_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
        </div>
        {!pending && (
          <p className="muted" style={{ margin: "6px 0 0" }}>
            등록 가능: {user.permissions.map((p) => PERMISSION_LABELS[p] ?? p).join(", ") || "-"} (업무 구분 기본 + 승인된 권한 요청)
          </p>
        )}
      </div>
      <div className="user-edit-block">
        <strong>도메인</strong>
        {isAdminRole ? (
          <p className="muted">플랫폼 관리자는 모든 도메인에 접근합니다.</p>
        ) : (
          <>
            <label className="check" style={{ margin: "6px 0" }}>
              <input type="checkbox" checked={useDefault} onChange={(e) => setUseDefault(e.target.checked)} />
              소속 파트너사의 도메인을 그대로 사용
            </label>
            <div className="table-wrap">
              <table style={{ minWidth: 0, maxWidth: 520 }}>
                <thead><tr><th style={{ width: 70 }}>사용</th><th>벤더 도메인</th><th>파트너사 기본</th></tr></thead>
                <tbody>
                  {(vendors.data ?? []).map((v) => {
                    const on = useDefault ? partnerVendorIds.has(v.id) : domainIds.has(v.id);
                    return (
                      <tr key={v.id}>
                        <td><input type="checkbox" checked={on} disabled={useDefault} onChange={() => toggleDomain(v.id)} aria-label={`${v.name} 도메인`} /></td>
                        <td>{v.name}</td>
                        <td className="muted">{partnerVendorIds.has(v.id) ? "포함" : "-"}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            {useDefault && <p className="muted">사용자별로 고르려면 위 체크를 끄세요.</p>}
          </>
        )}
      </div>
      <div className="actions">
        <button className="primary" disabled={save.isPending} onClick={() => save.mutate()}>{pending ? "승인" : "변경 저장"}</button>
        <button onClick={onDone}>취소</button>
      </div>
      {save.error && <p className="error">{save.error.message}</p>}
    </div>
  );
}

function PartnersAndVendors() {
  const queryClient = useQueryClient();
  const partners = useQuery({ queryKey: ["admin", "partners"], queryFn: () => api<Partner[]>("/admin/partners") });
  const vendors = useQuery({ queryKey: ["vendors"], queryFn: () => api<Vendor[]>("/vendors") });
  const [partnerName, setPartnerName] = useState("");
  const [vendorName, setVendorName] = useState("");

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin", "partners"] });
    queryClient.invalidateQueries({ queryKey: ["vendors"] });
    queryClient.invalidateQueries({ queryKey: ["me"] });
  };
  const createPartner = useMutation({
    mutationFn: () => api("/admin/partners", { method: "POST", json: { name: partnerName } }),
    onSuccess: () => { setPartnerName(""); invalidate(); },
  });
  const createVendor = useMutation({
    mutationFn: () => api("/admin/vendors", { method: "POST", json: { name: vendorName } }),
    onSuccess: () => { setVendorName(""); invalidate(); },
  });
  const setVendors = useMutation({
    mutationFn: ({ partner, vendorIds }: { partner: Partner; vendorIds: number[] }) =>
      api(`/admin/partners/${partner.id}/vendors`, { method: "PUT", json: { vendor_ids: vendorIds } }),
    onSuccess: invalidate,
  });

  function toggleVendor(partner: Partner, vendorId: number) {
    const current = partner.vendors.map((v) => v.id);
    const next = current.includes(vendorId) ? current.filter((v) => v !== vendorId) : [...current, vendorId];
    setVendors.mutate({ partner, vendorIds: next });
  }

  const submit = (fn: () => void) => (e: FormEvent) => {
    e.preventDefault();
    fn();
  };
  const error = createPartner.error ?? createVendor.error ?? setVendors.error;

  return (
    <section className="card">
      <h2>파트너사 · 벤더 도메인</h2>
      <div className="form-row">
        <form className="form-row" style={{ flex: 1 }} onSubmit={submit(() => createVendor.mutate())}>
          <label>새 벤더 도메인<input value={vendorName} onChange={(e) => setVendorName(e.target.value)} required /></label>
          <button>추가</button>
        </form>
        <form className="form-row" style={{ flex: 1 }} onSubmit={submit(() => createPartner.mutate())}>
          <label>새 파트너사<input value={partnerName} onChange={(e) => setPartnerName(e.target.value)} required /></label>
          <button>추가</button>
        </form>
      </div>
      {error && <p className="error">{error.message}</p>}
      <p className="muted">파트너사는 체크한 벤더 도메인의 문서와 커뮤니티에만 접근합니다.</p>
      <div className="table-wrap">
        <table>
          <thead><tr><th>파트너사</th><th>지원 벤더 도메인</th></tr></thead>
          <tbody>
            {partners.data?.map((p) => (
              <tr key={p.id}>
                <td>{p.name}</td>
                <td className="actions">
                  {vendors.data?.map((v) => (
                    <label key={v.id} className="check">
                      <input type="checkbox" checked={p.vendors.some((pv) => pv.id === v.id)} onChange={() => toggleVendor(p, v.id)} />
                      {v.name}
                    </label>
                  ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function AiUsage() {
  const usage = useQuery({ queryKey: ["admin", "usage"], queryFn: () => api<UsageOverview>("/admin/usage") });
  if (!usage.data) return null;
  const u = usage.data;
  const usd = (v: number) => `$${v.toFixed(2)}`;
  return (
    <section className="card">
      <h2>AI 사용량 · 회사별 한도</h2>
      <p className="muted">
        {u.month} 추정 비용 <strong>{usd(u.cost_usd)}</strong>
        {u.budget_usd ? ` / 월 예산 ${usd(u.budget_usd)}` : " (월 예산 제한 없음)"} · 요약 엔진 {u.llm_provider}
        <br />
        회사 기본 한도 월 {u.default_quota_pages.toLocaleString()}쪽 · 재생성 사용자당 하루 {u.daily_regenerate_limit}회 · 1쪽 = 원문{" "}
        {u.chars_per_page.toLocaleString()}자. 플랫폼 관리자는 회사 한도에서 제외됩니다
        {u.unassigned.used_pages ? ` (이번 달 ${u.unassigned.used_pages.toLocaleString()}쪽, ${usd(u.unassigned.cost_usd)})` : ""}.
      </p>
      <div className="table-wrap">
        <table style={{ minWidth: 720 }}>
          <thead>
            <tr>
              <th>회사</th>
              <th>이번 달 사용 / 한도</th>
              <th>토큰 (입력 / 출력)</th>
              <th>추정 비용</th>
              <th>월 한도 변경 (쪽)</th>
            </tr>
          </thead>
          <tbody>
            {u.partners.map((p) => <PartnerUsageRow key={p.id} row={p} />)}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PartnerUsageRow({ row }: { row: PartnerUsage }) {
  const queryClient = useQueryClient();
  const [value, setValue] = useState(row.custom_quota ? String(row.quota_pages) : "");
  const save = useMutation({
    mutationFn: (quota: number | null) =>
      api(`/admin/partners/${row.id}/quota`, { method: "PUT", json: { monthly_page_quota: quota } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "usage"] }),
  });
  const ratio = row.quota_pages ? row.used_pages / row.quota_pages : 0;
  return (
    <tr>
      <td>{row.name}</td>
      <td className={ratio >= 1 ? "error" : ""}>
        {row.used_pages.toLocaleString()} / {row.quota_pages.toLocaleString()}쪽{row.custom_quota ? "" : " (기본)"}
      </td>
      <td className="muted">{row.input_tokens.toLocaleString()} / {row.output_tokens.toLocaleString()}</td>
      <td>${row.cost_usd.toFixed(2)}</td>
      <td>
        <form
          className="form-row"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(value.trim() === "" ? null : Number(value));
          }}
        >
          <input type="number" min={0} placeholder="기본값" value={value} onChange={(e) => setValue(e.target.value)} style={{ width: 90 }} />
          <button disabled={save.isPending}>저장</button>
        </form>
        {save.error && <p className="error">{save.error.message}</p>}
      </td>
    </tr>
  );
}
