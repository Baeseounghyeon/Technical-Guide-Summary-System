import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { ROLE_LABELS } from "../labels";
import type { Partner, Role, User, Vendor } from "../types";

export default function AdminPage() {
  return (
    <>
      <div className="page-header">
        <h1>관리자</h1>
        <p className="muted">가입 승인, 파트너사와 벤더 도메인을 관리합니다.</p>
      </div>
      <PendingUsers />
      <PartnersAndVendors />
    </>
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
