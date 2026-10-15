import type { ReactNode } from "react";
import { Link, Navigate, NavLink, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth";
import { ROLE_LABELS } from "./labels";
import AdminPage from "./pages/AdminPage";
import DocumentPage from "./pages/DocumentPage";
import DocumentsPage from "./pages/DocumentsPage";
import GuidePage from "./pages/GuidePage";
import LoginPage from "./pages/LoginPage";
import SignupPage from "./pages/SignupPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/" element={<Protected><DocumentsPage /></Protected>} />
      <Route path="/documents/:id" element={<Protected><DocumentPage /></Protected>} />
      <Route path="/guides/:id" element={<Protected><GuidePage /></Protected>} />
      <Route path="/admin" element={<Protected admin><AdminPage /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

function Protected({ children, admin }: { children: ReactNode; admin?: boolean }) {
  const { me, loading, logout } = useAuth();
  if (loading) return <p className="page">불러오는 중…</p>;
  if (!me) return <Navigate to="/login" replace />;
  if (admin && me.role !== "platform_admin") return <Navigate to="/" replace />;

  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">기술 가이드 요약</Link>
        <nav>
          <NavLink to="/" end>문서</NavLink>
          {me.role === "platform_admin" && <NavLink to="/admin">관리자</NavLink>}
        </nav>
        <span className="who">
          {me.name} · {me.partner_name ?? ROLE_LABELS[me.role]}
          <button className="link" onClick={logout}>로그아웃</button>
        </span>
      </header>
      <main className="page">{children}</main>
    </>
  );
}
