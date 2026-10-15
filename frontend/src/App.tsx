import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "./auth";
import { ROLE_LABELS } from "./labels";
import AdminPage from "./pages/AdminPage";
import CommunityPage from "./pages/CommunityPage";
import DomainPage from "./pages/DomainPage";
import PostPage from "./pages/PostPage";
import DocumentPage from "./pages/DocumentPage";
import DocumentsPage from "./pages/DocumentsPage";
import GuidePage from "./pages/GuidePage";
import LoginPage from "./pages/LoginPage";
import PartnerGuidePage from "./pages/PartnerGuidePage";
import SettingsPage from "./pages/SettingsPage";
import SignupPage from "./pages/SignupPage";
import type { Role } from "./types";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/" element={<Protected><DocumentsPage /></Protected>} />
      <Route path="/documents/:id" element={<Protected><DocumentPage /></Protected>} />
      <Route path="/guides/:id" element={<Protected><GuidePage /></Protected>} />
      <Route path="/partner-guides/:id" element={<Protected><PartnerGuidePage /></Protected>} />
      <Route path="/community" element={<Protected><CommunityPage /></Protected>} />
      <Route path="/community/:vendorId" element={<Protected><DomainPage /></Protected>} />
      <Route path="/community/posts/:id" element={<Protected><PostPage /></Protected>} />
      <Route path="/admin" element={<Protected roles={["platform_admin"]}><AdminPage /></Protected>} />
      <Route path="/settings" element={<Protected roles={SETTINGS_ROLES}><SettingsPage /></Protected>} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

const SETTINGS_ROLES: Role[] = ["platform_admin", "partner_admin"];

function Protected({ children, roles }: { children: ReactNode; roles?: Role[] }) {
  const { me, loading } = useAuth();
  if (loading) return <p className="page">불러오는 중…</p>;
  if (!me) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(me.role)) return <Navigate to="/" replace />;

  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand">
          <span className="brand-mark">TG</span>
          기술 가이드 요약
        </Link>
        <nav>
          <NavLink to="/" end>문서</NavLink>
          <NavLink to="/community">커뮤니티</NavLink>
          {SETTINGS_ROLES.includes(me.role) && <NavLink to="/settings">설정</NavLink>}
          {me.role === "platform_admin" && <NavLink to="/admin">관리자</NavLink>}
        </nav>
        <UserMenu />
      </header>
      <main className="page">{children}</main>
      <HashScroll />
    </>
  );
}

/** 주소의 #앵커(예: /settings#logo)로 스크롤한다. 데이터가 늦게 그려지는 경우를 위해 잠시 재시도한다. */
function HashScroll() {
  const { pathname, hash } = useLocation();
  useEffect(() => {
    if (!hash) return;
    let tries = 0;
    const timer = window.setInterval(() => {
      const el = document.getElementById(hash.slice(1));
      if (el || ++tries > 20) {
        window.clearInterval(timer);
        el?.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }, 100);
    return () => window.clearInterval(timer);
  }, [pathname, hash]);
  return null;
}

/** 이름을 누르면 열리는 메뉴: 내 정보, 회사 로고 변경, 권한 신청, 로그아웃. */
function UserMenu() {
  const { me, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  if (!me) return null;
  const go = (path: string) => {
    setOpen(false);
    navigate(path);
  };
  const canManageLogo = SETTINGS_ROLES.includes(me.role);
  // 이름이 권한 이름과 같으면(예: 관리자 계정 이름 "플랫폼 관리자") 한 번만 보여 준다.
  const roleLabel = ROLE_LABELS[me.role] === me.name ? null : ROLE_LABELS[me.role];
  const subtitle = [roleLabel, me.partner_name].filter(Boolean).join(" · ");

  return (
    <div className="user-menu" ref={ref}>
      <button className="user-button" onClick={() => setOpen(!open)} aria-haspopup="menu" aria-expanded={open}>
        <span className="avatar">{me.name.slice(0, 1)}</span>
        <span className="user-name">{me.name}</span>
        <span className="chevron">▾</span>
      </button>
      {open && (
        <div className="dropdown" role="menu">
          <div className="dropdown-head">
            <strong>{me.name}</strong>
            <span className="muted">{me.email}</span>
            {subtitle && <div className="muted">{subtitle}</div>}
          </div>
          {canManageLogo && (
            <button className="dropdown-item" role="menuitem" onClick={() => go("/settings#logo")}>회사 로고·양식 변경</button>
          )}
          {me.role !== "platform_admin" && (
            <button className="dropdown-item" role="menuitem" onClick={() => go("/community#access")}>다른 도메인 권한 신청</button>
          )}
          {me.role === "platform_admin" && (
            <button className="dropdown-item" role="menuitem" onClick={() => go("/admin")}>관리자 페이지</button>
          )}
          <div className="dropdown-sep" />
          <button
            className="dropdown-item danger"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              logout();
            }}
          >
            로그아웃
          </button>
        </div>
      )}
    </div>
  );
}
