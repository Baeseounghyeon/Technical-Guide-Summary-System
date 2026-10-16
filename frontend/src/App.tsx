import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import logoUrl from "./assets/unipoint-logo.png";
import { useAuth } from "./auth";
import ColumnResizer from "./ColumnResizer";
import { ROLE_LABELS, TRACK_LABELS } from "./labels";
import AdminPage from "./pages/AdminPage";
import CommunityPage from "./pages/CommunityPage";
import DashboardPage from "./pages/DashboardPage";
import DomainPage from "./pages/DomainPage";
import PostPage from "./pages/PostPage";
import DocumentPage from "./pages/DocumentPage";
import DocumentsPage, { RegisteredDocumentsPage } from "./pages/DocumentsPage";
import GuidePage from "./pages/GuidePage";
import GuidesPage, { OrgTypePage, RegisteredTypePage } from "./pages/GuidesPage";
import LoginPage from "./pages/LoginPage";
import PartnerGuidePage from "./pages/PartnerGuidePage";
import QuotesPage from "./pages/QuotesPage";
import { DomainRequestPage, MyRequestsPage } from "./pages/RequestsPages";
import { PermissionRequestPage } from "./pages/PermissionPages";
import GuideSharePage from "./pages/GuideSharePage";
import HomeDetailPage from "./pages/HomeDetailPage";
import TrashPage from "./pages/TrashPage";
import NotificationBell from "./NotificationBell";
import SettingsPage from "./pages/SettingsPage";
import SharedPage from "./pages/SharedPage";
import SignupPage from "./pages/SignupPage";
import type { Role } from "./types";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route path="/" element={<Protected><DashboardPage /></Protected>} />
      <Route path="/home/:view" element={<Protected><HomeDetailPage /></Protected>} />
      <Route path="/trash" element={<Protected><TrashPage /></Protected>} />
      <Route path="/documents" element={<Protected><DocumentsPage /></Protected>} />
      <Route path="/documents/registered" element={<Protected><RegisteredDocumentsPage /></Protected>} />
      <Route path="/my-requests" element={<Navigate to="/requests" replace />} />
      <Route path="/requests" element={<Protected><MyRequestsPage /></Protected>} />
      <Route path="/requests/approvals" element={<Protected><PermissionRequestPage /></Protected>} />
      <Route path="/requests/domain" element={<Protected><DomainRequestPage /></Protected>} />
      <Route path="/specs" element={<Protected><RegisteredTypePage key="spec" docType="spec" /></Protected>} />
      <Route path="/specs/org" element={<Protected><OrgTypePage key="spec-org" docType="spec" /></Protected>} />
      <Route path="/brochures" element={<Protected><RegisteredTypePage key="brochure" docType="brochure" /></Protected>} />
      <Route path="/brochures/org" element={<Protected><OrgTypePage key="brochure-org" docType="brochure" /></Protected>} />
      <Route path="/documents/:id" element={<Protected><DocumentPage /></Protected>} />
      <Route path="/guides" element={<Protected><GuidesPage /></Protected>} />
      <Route path="/guides/org" element={<Protected><OrgTypePage key="guide-org" docType="guide" /></Protected>} />
      <Route path="/guides/share" element={<Protected><GuideSharePage /></Protected>} />
      <Route path="/guides/:id" element={<Protected><GuidePage /></Protected>} />
      <Route path="/partner-guides/:id" element={<Protected><PartnerGuidePage /></Protected>} />
      <Route path="/shared" element={<Protected><SharedPage /></Protected>} />
      <Route path="/quotes" element={<Protected><RegisteredTypePage key="quote" docType="quote" /></Protected>} />
      <Route path="/quotes/org" element={<Protected><OrgTypePage key="quote-org" docType="quote" /></Protected>} />
      <Route path="/quotes/work" element={<Protected><QuotesPage /></Protected>} />
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

function Protected({ children, roles, sales }: { children: ReactNode; roles?: Role[]; sales?: boolean }) {
  const { me, loading } = useAuth();
  if (loading) return <p className="page">불러오는 중…</p>;
  if (!me) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(me.role)) return <Navigate to="/" replace />;
  // 업무 구분: 영업은 '가이드 공유' 대신 '견적서'. 플랫폼 관리자는 견적서도 본다(영업 마스터는 가이드 공유 없이).
  const isAdmin = me.role === "platform_admin";
  const isSales = me.track === "sales";
  if (sales && !isSales && !isAdmin) return <Navigate to="/" replace />;
  const can = (p: string) => isAdmin || me.permissions.includes(p);

  return (
    <>
      <header className="topbar">
        <Link to="/" className="brand" aria-label="unipoint 홈">
          <img src={logoUrl} alt="unipoint" />
        </Link>
        <nav>
          <NavLink to="/" end>홈</NavLink>
          <DocsMenu />
          {/* 등록 권한이 있으면 '등록한 ○○', 없으면 같은 조직이 올린 것을 내려받기만 하는 '등록된 ○○' */}
          <TypeMenu base="/specs" label="규격서" canEdit={can("spec")} />
          <GuidesMenu canEdit={can("guide")} />
          <TypeMenu base="/quotes" label="견적서" canEdit={can("quote")} work={can("quote")} />
          <TypeMenu base="/brochures" label="브로슈어" canEdit={can("brochure")} />
          <NavLink to="/community">커뮤니티</NavLink>
          <RequestsMenu isAdmin={isAdmin} />
          {SETTINGS_ROLES.includes(me.role) && (!isSales || isAdmin) && <NavLink to="/settings">설정</NavLink>}
          {me.role === "platform_admin" && <NavLink to="/admin">관리자</NavLink>}
        </nav>
        <div className="topbar-right">
          <NotificationBell />
          <UserMenu />
        </div>
      </header>
      <main className="page">{children}</main>
      <HashScroll />
      <ColumnResizer />
    </>
  );
}

type MenuItem = { key: string; label: string; to: string; active: boolean };

/** 상단 '문서' 메뉴: 누르면 문서 등록, 마우스를 올리면 문서 등록·등록한 문서. */
function DocsMenu() {
  const { pathname } = useLocation();
  const items = [
    { key: "upload", label: "문서 등록", to: "/documents", active: pathname === "/documents" },
    { key: "registered", label: "등록한 문서", to: "/documents/registered", active: pathname === "/documents/registered" },
  ];
  return <HoverMenu to="/documents" label="문서" items={items} />;
}

/** 상단 '규격서'·'견적서'·'브로슈어' 메뉴: 누르면 등록한(권한 없으면 등록된) ○○, 마우스를 올리면 그것과 조직 요청 ○○.
 *  견적서는 권한이 있으면 '견적서 작업'(양식·로고·자료·생성)도 보인다. */
function TypeMenu({ base, label, canEdit, work = false }: { base: string; label: string; canEdit: boolean; work?: boolean }) {
  const { pathname } = useLocation();
  const items = [
    { key: "registered", label: `${canEdit ? "등록한" : "등록된"} ${label}`, to: base, active: pathname === base },
    { key: "org", label: `조직 요청 ${label}`, to: `${base}/org`, active: pathname === `${base}/org` },
    ...(work ? [{ key: "work", label: `${label} 작업`, to: `${base}/work`, active: pathname === `${base}/work` }] : []),
  ];
  return <HoverMenu to={base} label={label} items={items} />;
}

/** 상단 '가이드' 메뉴: 누르면 등록한 가이드, 마우스를 올리면 가이드 등록·등록한 가이드·조직 요청 가이드·가이드 공유. */
function GuidesMenu({ canEdit }: { canEdit: boolean }) {
  const { pathname, search } = useLocation();
  const items = [
    ...(canEdit ? [{ key: "upload", label: "가이드 등록", to: "/documents?type=guide", active: pathname === "/documents" && search.includes("type=guide") }] : []),
    { key: "registered", label: canEdit ? "등록한 가이드" : "등록된 가이드", to: "/guides", active: pathname === "/guides" },
    { key: "org", label: "조직 요청 가이드", to: "/guides/org", active: pathname === "/guides/org" },
    ...(canEdit ? [{ key: "share", label: "가이드 공유", to: "/guides/share", active: pathname === "/guides/share" }] : []),
  ];
  return <HoverMenu to="/guides" label="가이드" items={items} alsoActive={pathname === "/shared"} />;
}

/** 상단 '요청' 메뉴: 누르면 작업 내역, 마우스를 올리면 작업 내역·권한 승인 요청·도메인 권한 요청(일반 사용자). */
function RequestsMenu({ isAdmin }: { isAdmin: boolean }) {
  const { pathname } = useLocation();
  const items = [
    { key: "mine", label: "작업 내역", to: "/requests", active: pathname === "/requests" },
    { key: "approvals", label: "권한 승인 요청", to: isAdmin ? "/admin#permission-requests" : "/requests/approvals", active: pathname === "/requests/approvals" },
    ...(isAdmin ? [] : [{ key: "domain", label: "도메인 권한 요청", to: "/requests/domain", active: pathname === "/requests/domain" }]),
  ];
  return <HoverMenu to="/requests" label="요청" items={items} />;
}

/** 마우스를 올리면 하위 메뉴가 펼쳐지는 상단 메뉴.
 *  메뉴 줄이 가로 스크롤 영역이라 잘리지 않도록 펼침 목록은 body 에 띄운다. */
function HoverMenu({ to, label, items, alsoActive = false }: { to: string; label: string; items: MenuItem[]; alsoActive?: boolean }) {
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  const linkRef = useRef<HTMLAnchorElement>(null);
  const timer = useRef<number | undefined>(undefined);
  const [pos, setPos] = useState<{ left: number; top: number } | null>(null);

  const show = () => {
    window.clearTimeout(timer.current);
    const r = linkRef.current?.getBoundingClientRect();
    if (r) setPos({ left: r.left + r.width / 2, top: r.bottom });
  };
  // 링크에서 목록으로 마우스를 옮기는 동안 닫히지 않게 잠깐 기다린다.
  const hide = () => {
    timer.current = window.setTimeout(() => setPos(null), 150);
  };
  useEffect(() => setPos(null), [pathname, search]);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  return (
    <>
      <NavLink
        ref={linkRef}
        to={to}
        className={({ isActive }) => (isActive || alsoActive ? "active" : "")}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        aria-haspopup="menu"
      >
        {label}
      </NavLink>
      {pos &&
        createPortal(
          <div className="dropdown nav-dropdown" role="menu" style={{ left: pos.left, top: pos.top }} onMouseEnter={show} onMouseLeave={hide}>
            {items.map((item) => (
              <button
                key={item.key}
                className={`dropdown-item${item.active ? " active" : ""}`}
                role="menuitem"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => navigate(item.to)}
              >
                {item.label}
              </button>
            ))}
          </div>,
          document.body,
        )}
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
  const trackLabel = me.role === "platform_admin" && me.track !== "sales" ? null : TRACK_LABELS[me.track ?? "engineer"];
  const subtitle = [trackLabel, roleLabel, me.partner_name].filter(Boolean).join(" · ");
  const isSales = me.track === "sales" && me.role !== "platform_admin";

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
            <button className="dropdown-item" role="menuitem" onClick={() => go(isSales ? "/quotes/work?tab=logo" : "/settings#logo")}>
              {isSales ? "견적서 로고·양식 변경" : "회사 로고·양식 변경"}
            </button>
          )}
          <button className="dropdown-item" role="menuitem" onClick={() => go("/requests")}>작업 내역</button>
          <button className="dropdown-item" role="menuitem" onClick={() => go("/trash")}>휴지통</button>
          {me.role !== "platform_admin" && (
            <button className="dropdown-item" role="menuitem" onClick={() => go("/requests/domain")}>도메인 권한 요청</button>
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
