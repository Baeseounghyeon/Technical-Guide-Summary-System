import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";

const EMPTY = { email: "", password: "", name: "", company_name: "", department: "", phone: "" };

export default function SignupPage() {
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const set = (key: keyof typeof EMPTY) => (e: { target: { value: string } }) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await api("/auth/signup", { method: "POST", json: form });
      setDone(true);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="page">
      <div className="card auth-card">
        <h1>가입 신청</h1>
        {done ? (
          <>
            <p>신청이 접수되었습니다. 관리자가 소속 파트너사와 벤더 도메인을 확인해 승인하면 로그인할 수 있습니다.</p>
            <Link to="/login">로그인 화면으로</Link>
          </>
        ) : (
          <form className="form" onSubmit={submit}>
            <label>이메일<input type="email" value={form.email} onChange={set("email")} required /></label>
            <label>비밀번호 (8자 이상)<input type="password" minLength={8} value={form.password} onChange={set("password")} required /></label>
            <label>이름<input value={form.name} onChange={set("name")} required /></label>
            <label>소속 회사<input value={form.company_name} onChange={set("company_name")} required /></label>
            <label>부서<input value={form.department} onChange={set("department")} /></label>
            <label>연락처<input value={form.phone} onChange={set("phone")} /></label>
            {error && <p className="error">{error}</p>}
            <button className="primary">신청</button>
            <p className="muted"><Link to="/login">로그인 화면으로</Link></p>
          </form>
        )}
      </div>
    </div>
  );
}
