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
import { MyRequestsPage } from "./pages/RequestsPages";
import { ApplyPage, ApprovalsPage } from "./pages/RequestCenterPages";
import { CreatedGuidesPage, GeneratedListPage, GuideCreatePage } from "./pages/GeneratePages";
import QuoteBuilderPage from "./pages/QuoteBuilderPage";
import HomeDetailPage from "./pages/HomeDetailPage";
import TrashPage from "./pages/TrashPage";
import NotificationBell from "./NotificationBell";
import SettingsPage from "./pages/SettingsPage";
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
      <Route path="/requests/apply" element={<Protected><ApplyPage /></Protected>} />
      <Route path="/requests/approvals" element={<Protected><ApprovalsPage /></Protected>} />
      {/* 예전 주소: 권한 신청·승인 처리로 합쳤다 */}
      <Route path="/requests/domain" element={<Navigate to="/requests/apply?kind=domain" replace />} />
      <Route path="/specs" element={<Protected><RegisteredTypePage key="spec" docType="spec" /></Protected>} />
      <Route path="/specs/org" element={<Protected><OrgTypePage key="spec-org" docType="spec" /></Protected>} />
      <Route path="/brochures" element={<Protected><RegisteredTypePage key="brochure" docType="brochure" /></Protected>} />
      <Route path="/brochures/org" element={<Protected><OrgTypePage key="brochure-org" docType="brochure" /></Protected>} />
      <Route path="/documents/:id" element={<Protected><DocumentPage /></Protected>} />
      <Route path="/guides" element={<Protected><GuidesPage /></Protected>} />
      <Route path="/guides/org" element={<Protected><OrgTypePage key="guide-org" docType="guide" /></Protected>} />
      <Route path="/guides/share" element={<Navigate to="/requests/apply?kind=share" replace />} />
      <Route path="/guides/create" element={<Protected perm="guide"><GuideCreatePage /></Protected>} />
      <Route path="/guides/created" element={<Protected perm="guide"><CreatedGuidesPage /></Protected>} />
      <Route path="/guides/:id" element={<Protected><GuidePage /></Protected>} />
      <Route path="/partner-guides/:id" element={<Protected><PartnerGuidePage /></Protected>} />
      <Route path="/shared" element={<SharedRedirect />} />
      <Route path="/quotes" element={<Protected><RegisteredTypePage key="quote" docType="quote" /></Protected>} />
      <Route path="/quotes/org" element={<Protected><OrgTypePage key="quote-org" docType="quote" /></Protected>} />
      <Route path="/quotes/work" element={<Protected><QuotesPage /></Protected>} />
      <Route path="/quotes/create" element={<Protected perm="quote"><QuoteBuilderPage /></Protected>} />
      <Route path="/quotes/created" element={<Protected perm="quote"><GeneratedListPage /></Protected>} />
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

/** 예전 가이드 받기 화면(/shared): 받은 요청은 승인 처리로, 나머지는 권한 신청 > 가이드 받기로. */
function SharedRedirect() {
  const { search } = useLocation();
  return <Navigate to={search.includes("incoming") ? "/requests/approvals?kind=download" : "/requests/apply?kind=download"} replace />;
}

/** perm: 그 권한(업무 구분 기본 + 승인된 권한)이 없으면 홈으로 보낸다. 예) 규격서·견적서 생성은 영업, 가이드 생성은 엔지니어. */
function Protected({ children, roles, sales, perm }: { children: ReactNode; roles?: Role[]; sales?: boolean; perm?: string }) {
  const { me, loading } = useAuth();
  if (loading) return <p className="page">불러오는 중…</p>;
  if (!me) return <Navigate to="/login" replace />;
  if (roles && !roles.includes(me.role)) return <Navigate to="/" replace />;
  // 업무 구분: 영업은 '가이드 공유' 대신 '견적서'. 플랫폼 관리자는 견적서도 본다(영업 마스터는 가이드 공유 없이).
  const isAdmin = me.role === "platform_admin";
  const isSales = me.track === "sales";
  if (sales && !isSales && !isAdmin) return <Navigate to="/" replace />;
  const can = (p: string) => isAdmin || me.permissions.includes(p);
  if (perm && !can(perm)) return <Navigate to="/" replace />;

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
          <MaterialsMenu canEditSpec={can("spec")} canEditBrochure={can("brochure")} />
          <GuidesMenu canEdit={can("guide")} />
          <TypeMenu base="/quotes" label="견적서" canEdit={can("quote")} create />
          <NavLink to="/community">커뮤니티</NavLink>
          <RequestsMenu canApprove={isAdmin || me.role === "partner_admin" || can("guide")} />
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

/** 상단 '자료' 메뉴: 규격서·브로슈어는 목록만 있어 한 메뉴로 묶는다. 누르면 규격서 목록.
 *  권한이 있으면 '등록한 ○○', 없으면 같은 조직 것을 내려받기만 하는 '등록된 ○○'. */
function MaterialsMenu({ canEditSpec, canEditBrochure }: { canEditSpec: boolean; canEditBrochure: boolean }) {
  const { pathname } = useLocation();
  const items = [
    { key: "spec", label: `${canEditSpec ? "등록한" : "등록된"} 규격서`, to: "/specs", active: pathname === "/specs" },
    { key: "spec-org", label: "조직 요청 규격서", to: "/specs/org", active: pathname === "/specs/org" },
    { key: "brochure", label: `${canEditBrochure ? "등록한" : "등록된"} 브로슈어`, to: "/brochures", active: pathname === "/brochures" },
    { key: "brochure-org", label: "조직 요청 브로슈어", to: "/brochures/org", active: pathname === "/brochures/org" },
  ];
  return <HoverMenu to="/specs" label="자료" items={items} alsoActive={pathname.startsWith("/brochures")} />;
}

/** 상단 '견적서' 메뉴: 누르면 등록한(권한 없으면 등록된) 견적서, 마우스를 올리면 그것과 조직 요청 견적서.
 *  생성·생성한 ○○ 은 그 종류의 등록 권한이 있을 때만 보인다. */
function TypeMenu({ base, label, canEdit, create = false }: { base: string; label: string; canEdit: boolean; create?: boolean }) {
  const { pathname } = useLocation();
  // 생성·생성한 ○○ 은 그 종류의 권한이 있을 때만 (엔지니어·영업 롤 구분: 규격서·견적서는 영업)
  const making = create && canEdit;
  const items = [
    ...(making ? [{ key: "create", label: `${label} 생성`, to: `${base}/create`, active: pathname === `${base}/create` }] : []),
    { key: "registered", label: `${canEdit ? "등록한" : "등록된"} ${label}`, to: base, active: pathname === base },
    { key: "org", label: `조직 요청 ${label}`, to: `${base}/org`, active: pathname === `${base}/org` },
    ...(making ? [{ key: "created", label: `생성한 ${label}`, to: `${base}/created`, active: pathname === `${base}/created` }] : []),
  ];
  return <HoverMenu to={base} label={label} items={items} />;
}

/** 상단 '가이드' 메뉴: 누르면 등록한 가이드, 마우스를 올리면 가이드 생성·등록한 가이드·조직 요청 가이드·생성한 가이드·가이드 공유.
 *  가이드 문서 올리기는 '문서 > 문서 등록'에서 한다 (같은 기능이라 가이드 메뉴의 '가이드 등록'은 뺐다). */
function GuidesMenu({ canEdit }: { canEdit: boolean }) {
  const { pathname } = useLocation();
  const items = [
    ...(canEdit ? [{ key: "create", label: "가이드 생성", to: "/guides/create", active: pathname === "/guides/create" }] : []),
    { key: "registered", label: canEdit ? "등록한 가이드" : "등록된 가이드", to: "/guides", active: pathname === "/guides" },
    { key: "org", label: "조직 요청 가이드", to: "/guides/org", active: pathname === "/guides/org" },
    ...(canEdit ? [{ key: "created", label: "생성한 가이드", to: "/guides/created", active: pathname === "/guides/created" }] : []),
  ];
  return <HoverMenu to="/guides" label="가이드" items={items} />;
}

/** 상단 '요청' 메뉴: 누르면 작업 내역, 마우스를 올리면 작업 내역·권한 신청(기능 권한·도메인 열람·가이드 받기·가이드 공유)·승인 처리.
 *  승인 처리는 승인할 수 있는 사람(관리자, 파트너 관리자, 가이드를 올리는 사람)에게만 보인다. */
function RequestsMenu({ canApprove }: { canApprove: boolean }) {
  const { pathname } = useLocation();
  const items = [
    { key: "mine", label: "작업 내역", to: "/requests", active: pathname === "/requests" },
    { key: "apply", label: "권한 신청", to: "/requests/apply", active: pathname === "/requests/apply" },
    ...(canApprove ? [{ key: "approvals", label: "승인 처리", to: "/requests/approvals", active: pathname === "/requests/approvals" }] : []),
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
            <button className="dropdown-item" role="menuitem" onClick={() => go(isSales ? "/quotes/create" : "/settings#logo")}>
              {isSales ? "견적서 양식 변경" : "회사 로고·양식 변경"}
            </button>
          )}
          <button className="dropdown-item" role="menuitem" onClick={() => go("/requests")}>작업 내역</button>
          <button className="dropdown-item" role="menuitem" onClick={() => go("/trash")}>휴지통</button>
          <button className="dropdown-item" role="menuitem" onClick={() => go("/requests/apply")}>권한 신청</button>
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
