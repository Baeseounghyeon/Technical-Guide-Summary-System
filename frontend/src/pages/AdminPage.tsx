import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { GRANT_STATUS, ROLE_LABELS } from "../labels";
import type { AccessGrant, AdminUser, Partner, Role, User, Vendor } from "../types";

export default function AdminPage() {
  return (
    <>
      <div className="page-header">
        <h1>관리자</h1>
        <p className="muted">가입 승인, 파트너사와 벤더 도메인을 관리합니다.</p>
      </div>
      <PendingUsers />
      <Members />
      <AccessRequests />
      <PartnersAndVendors />
    </>
  );
}

function Members() {
  const [statusFilter, setStatusFilter] = useState("");
  const [q, setQ] = useState("");
  const users = useQuery({
    queryKey: ["admin", "users", "all", statusFilter],
    queryFn: () => api<AdminUser[]>(`/admin/users${statusFilter ? `?status=${statusFilter}` : ""}`),
  });
  const keyword = q.trim().toLowerCase();
  const shown = (users.data ?? []).filter(
    (u) => !keyword || [u.name, u.email, u.partner_name, u.company_name].some((v) => v?.toLowerCase().includes(keyword)),
  );

  return (
    <section className="card">
      <h2>가입자</h2>
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
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>이름</th><th>가입 일시</th><th>메일</th><th>전화번호</th><th>소속</th><th>할당된 도메인</th><th>권한</th><th>상태</th></tr>
          </thead>
          <tbody>
            {shown.map((u) => (
              <tr key={u.id}>
                <td style={{ whiteSpace: "nowrap" }}>{u.name}</td>
                <td style={{ whiteSpace: "nowrap" }}>{new Date(u.created_at).toLocaleString()}</td>
                <td>{u.email}</td>
                <td style={{ whiteSpace: "nowrap" }}>{u.phone || "-"}</td>
                <td>
                  {u.partner_name ?? <span className="muted">미지정</span>}
                  {(u.department || (!u.partner_name && u.company_name)) && (
                    <div className="muted">{[u.department, !u.partner_name && u.company_name ? `신청: ${u.company_name}` : null].filter(Boolean).join(" · ")}</div>
                  )}
                </td>
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
                <td style={{ whiteSpace: "nowrap" }}>{ROLE_LABELS[u.role]}</td>
                <td><span className={`badge ${u.status}`}>{USER_STATUS[u.status]}</span></td>
              </tr>
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
    <section className="card">
      <div className="summary-head">
        <h2 style={{ margin: 0 }}>타 도메인 열람 신청</h2>
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
                    <div className="muted">사유: {g.reason}</div>
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
        <strong>{grant.user.name}</strong> <span className="muted">{grant.user_email}</span>
        <div className="muted">{grant.user.partner_name} → <strong>{grant.vendor_name}</strong> · {new Date(grant.created_at).toLocaleDateString()}</div>
        <div>사유: {grant.reason}</div>
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

function PendingUsers() {
  const users = useQuery({ queryKey: ["admin", "users", "pending"], queryFn: () => api<User[]>("/admin/users?status=pending") });
  const partners = useQuery({ queryKey: ["admin", "partners"], queryFn: () => api<Partner[]>("/admin/partners") });

  return (
    <section className="card">
      <h2>가입 승인 대기</h2>
      {users.data?.length === 0 && <p className="muted">대기 중인 신청이 없습니다.</p>}
      <div className="table-wrap">
        <table>
          <tbody>
            {users.data?.map((u) => <PendingRow key={u.id} user={u} partners={partners.data ?? []} />)}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PendingRow({ user, partners }: { user: User; partners: Partner[] }) {
  const queryClient = useQueryClient();
  // 사용자가 고르기 전에는 신청 회사명과 같은 파트너사를 제안한다 (목록이 늦게 와도 반영되도록 매번 계산).
  const [chosen, setPartnerId] = useState<number | "" | undefined>(undefined);
  const partnerId = chosen ?? partners.find((p) => p.name === user.company_name)?.id ?? "";
  const [role, setRole] = useState<Role>("engineer");
  const approve = useMutation({
    mutationFn: () =>
      api(`/admin/users/${user.id}/approve`, {
        method: "POST",
        json: { partner_id: partnerId === "" ? null : partnerId, role },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] }),
  });

  return (
    <tr>
      <td>
        <strong>{user.name}</strong> <span className="muted">{user.email}</span>
        <div className="muted">신청 회사: {user.company_name} · {user.department ?? "-"} · {user.phone ?? "-"}</div>
        {approve.error && <div className="error">{approve.error.message}</div>}
      </td>
      <td>
        <select value={partnerId} onChange={(e) => setPartnerId(Number(e.target.value) || "")}>
          <option value="">파트너사 선택</option>
          {partners.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </td>
      <td>
        <select value={role} onChange={(e) => setRole(e.target.value as Role)}>
          {Object.entries(ROLE_LABELS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select>
      </td>
      <td><button className="primary" disabled={approve.isPending} onClick={() => approve.mutate()}>승인</button></td>
    </tr>
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
