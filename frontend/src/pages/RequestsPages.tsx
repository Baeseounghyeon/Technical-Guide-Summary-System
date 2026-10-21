import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import type { Domain } from "../types";
import { DocumentTable } from "./DocumentsPage";



/** 작업 내역: 내가 문서 등록에서 올린 문서. 상단 '요청' 메뉴와 사용자 메뉴에서 같은 화면으로 온다. */
export function MyRequestsPage() {
  const { me } = useAuth();
  return (
    <>
      <div className="page-header">
        <h1>작업 내역</h1>
        <p className="muted">내가 등록한 문서입니다. 문서 목적(규격서·가이드·견적서·브로슈어)과 등록 일자를 확인하고 내려받거나 삭제할 수 있습니다.</p>
      </div>
      <section className="card">
        {me && <DocumentTable query={`uploaded_by=${me.id}`} showDocType showStatus={false} />}
      </section>
    </>
  );
}

/** 도메인 열람 신청 양식: 다른 벤더 도메인 문서까지 볼 수 있도록 관리자에게 열람을 요청한다.
 *  이름·메일·회사명은 가입 정보로 미리 채우고 고칠 수 있다. */
export function DomainRequestForm() {
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const domains = useQuery({ queryKey: ["community", "domains"], queryFn: () => api<Domain[]>("/community/domains") });
  const today = new Date();
  const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  const [form, setForm] = useState({
    vendor_id: "",
    request_date: todayKey,
    reason: "",
    requester_name: me?.name ?? "",
    requester_email: me?.email ?? "",
    requester_company: me?.partner_name ?? me?.company_name ?? "",
  });
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const send = useMutation({
    mutationFn: () => {
      const { vendor_id, ...body } = form;
      return api(`/community/${vendor_id}/access-requests`, { method: "POST", json: body });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["access-requests"] });
      queryClient.invalidateQueries({ queryKey: ["community"] });
      setForm((f) => ({ ...f, vendor_id: "", reason: "" }));
    },
  });
  // 이미 소속이거나 열람 중인 도메인, 대기 중인 요청이 있는 도메인은 고를 수 없다.
  const options = (domains.data ?? []).filter((d) => d.access === "none");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    send.mutate();
  };
  return (
      <section className="card">
        <form className="form" onSubmit={submit}>
          <div className="form-row">
            <label>
              요청할 도메인(벤더)
              <select value={form.vendor_id} onChange={set("vendor_id")} required>
                <option value="">선택</option>
                {options.map((d) => <option key={d.vendor_id} value={d.vendor_id}>{d.vendor_name}{d.pending_request ? " (대기 중)" : ""}</option>)}
              </select>
            </label>
            <label style={{ flex: "0 0 200px" }}>요청 일자<input type="date" value={form.request_date} onChange={set("request_date")} required /></label>
          </div>
          <label>
            요청 목적
            <textarea value={form.reason} onChange={set("reason")} rows={3} required placeholder="예: 고객사 제안을 위해 Thales 도메인의 기술 가이드 열람 필요" />
          </label>
          <div className="form-row">
            <label>이름<input value={form.requester_name} onChange={set("requester_name")} required /></label>
            <label>메일 주소<input type="email" value={form.requester_email} onChange={set("requester_email")} required /></label>
            <label>회사명<input value={form.requester_company} onChange={set("requester_company")} required /></label>
          </div>
          {domains.data && options.length === 0 && <p className="muted">요청할 수 있는 다른 도메인이 없습니다.</p>}
          {send.error && <p className="error">{send.error.message}</p>}
          <div><button className="primary" disabled={send.isPending}>{send.isPending ? "보내는 중…" : "권한 요청 보내기"}</button></div>
        </form>
      </section>
  );
}
