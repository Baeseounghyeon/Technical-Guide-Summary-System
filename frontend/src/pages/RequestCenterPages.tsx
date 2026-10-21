import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useAuth } from "../auth";
import type { AccessGrant, DownloadRequest } from "../types";
import { AccessRequests } from "./AdminPage";
import { DownloadRequestsPanel, SharedGuidesPanel } from "./GuideRequestPanels";
import { GuideSharePanel } from "./GuideSharePage";
import { AdminPermissionRequests, PermissionRequestForm, STATUS_BADGE, STATUS_LABELS, type PermissionRequest } from "./PermissionPages";
import { DomainRequestForm } from "./RequestsPages";

type Kind = "permission" | "domain" | "download" | "share";

/** 신청 종류와 짧은 설명: 사용자가 무엇을 신청하는지, 누가 승인하는지 알 수 있게 한다. */
const KINDS: { key: Kind; label: string; desc: string; approver: string }[] = [
  {
    key: "permission",
    label: "기능 권한",
    desc: "지금 업무 구분에 없는 기능을 쓰려면 신청합니다. 예: 영업 담당이 가이드 요약을, 엔지니어가 견적서 생성을 함께 할 때.",
    approver: "관리자 승인",
  },
  {
    key: "domain",
    label: "도메인 열람",
    desc: "내 회사에 부여되지 않은 벤더 도메인(예: opentext)의 문서와 커뮤니티를 보려면 신청합니다.",
    approver: "관리자 승인 · 기간 열람 또는 회사에 정식 부여",
  },
  {
    key: "download",
    label: "가이드 받기",
    desc: "같은 벤더를 지원하는 다른 파트너사가 만든 가이드의 최종 문서(Word·PPT)를 내려받으려면 신청합니다.",
    approver: "그 가이드를 가진 회사의 관리자·작성자 승인",
  },
  {
    key: "share",
    label: "가이드 공유",
    desc: "내가 등록한 가이드를 다른 회사의 특정 사용자에게 보여 줍니다. 신청 없이 바로 공유되고 언제든 해제할 수 있습니다.",
    approver: "승인 없음",
  },
];
const isKind = (v: string | null): v is Kind => KINDS.some((k) => k.key === v);

/** 요청 > 권한 신청: 기능 권한·도메인 열람·가이드 받기 신청과 가이드 공유를 한 화면에서. 아래에 내 신청 내역. */
export function ApplyPage() {
  const { me } = useAuth();
  const [params, setParams] = useSearchParams();
  const kind: Kind = isKind(params.get("kind")) ? (params.get("kind") as Kind) : "permission";
  const current = KINDS.find((k) => k.key === kind)!;
  const isAdmin = me?.role === "platform_admin";

  return (
    <>
      <div className="page-header">
        <h1>권한 신청</h1>
        <p className="muted">필요한 것을 고르면 신청 양식이 나옵니다. 신청한 결과는 아래 '내 신청 내역'에서 봅니다.</p>
      </div>
      <div className="kind-grid" role="radiogroup" aria-label="신청 종류">
        {KINDS.map((k) => (
          <button
            key={k.key}
            role="radio"
            aria-checked={k.key === kind}
            className={`kind-card${k.key === kind ? " active" : ""}`}
            onClick={() => setParams({ kind: k.key })}
          >
            <strong>{k.label}</strong>
            <span className="kind-desc">{k.desc}</span>
            <span className="kind-approver">{k.approver}</span>
          </button>
        ))}
      </div>

      <h2 className="section-title">{current.label}</h2>
      {kind === "permission" &&
        (isAdmin ? <AdminNote what="모든 기능" /> : <PermissionRequestForm />)}
      {kind === "domain" && (isAdmin ? <AdminNote what="모든 도메인" /> : <DomainRequestForm />)}
      {kind === "download" && <SharedGuidesPanel />}
      {kind === "share" && <GuideSharePanel />}

      {kind !== "share" && <MyApplications />}
    </>
  );
}

function AdminNote({ what }: { what: string }) {
  return (
    <section className="card">
      <p className="muted" style={{ margin: 0 }}>관리자 계정은 {what}을 이미 가지고 있어 신청할 필요가 없습니다. 다른 사용자의 신청은 요청 &gt; 승인 처리에서 승인합니다.</p>
    </section>
  );
}

type Row = { key: string; kind: string; target: string; content: string; created: string; status: string; result: string; note: string | null };

/** 내 신청 내역: 기능 권한·도메인 열람·가이드 받기 신청을 한 표로. */
function MyApplications() {
  const { me } = useAuth();
  const perms = useQuery({ queryKey: ["permission-requests", "mine"], queryFn: () => api<PermissionRequest[]>("/permission-requests/mine") });
  const domains = useQuery({ queryKey: ["access-requests", "mine"], queryFn: () => api<AccessGrant[]>("/community/access-requests/mine") });
  const downloads = useQuery({
    queryKey: ["download-requests", "outgoing"],
    queryFn: () => api<DownloadRequest[]>("/download-requests/outgoing"),
    enabled: !!me?.partner_id,
  });
  const rows: Row[] = [
    ...(perms.data ?? []).map((r) => ({
      key: `p${r.id}`, kind: "기능 권한", target: r.scope_labels.join(", "), content: r.reason, created: r.created_at,
      status: r.status, result: STATUS_LABELS[r.status], note: r.decision_note,
    })),
    ...(domains.data ?? []).map((g) => ({
      key: `d${g.id}`, kind: "도메인 열람", target: g.vendor_name, content: g.reason, created: g.created_at, status: g.status,
      result:
        g.status !== "approved" ? STATUS_LABELS[g.status]
          : g.grant_type === "member" ? "승인 · 정식 부여"
            : g.expires_at ? `승인 · ~${new Date(g.expires_at).toLocaleDateString()}` : STATUS_LABELS[g.status],
      note: g.decision_note,
    })),
    ...(downloads.data ?? []).map((d) => ({
      key: `g${d.id}`, kind: "가이드 받기", target: `${d.guide_title} (${d.owner_partner_name})`, content: d.message ?? "", created: d.created_at,
      status: d.status, result: STATUS_LABELS[d.status], note: d.decision_note,
    })),
  ].sort((a, b) => b.created.localeCompare(a.created));
  const loading = perms.isLoading || domains.isLoading || downloads.isLoading;

  return (
    <section className="card">
      <h2 className="section-title">내 신청 내역</h2>
      {loading && <p className="muted">불러오는 중…</p>}
      {!loading && rows.length === 0 && <p className="muted">아직 신청한 것이 없습니다.</p>}
      {rows.length > 0 && (
        <div className="table-wrap">
          <table style={{ minWidth: 820 }}>
            <thead>
              <tr><th style={{ width: 100 }}>종류</th><th>대상</th><th>내용</th><th style={{ width: 100 }}>신청일</th><th style={{ width: 150 }}>결과</th><th>처리 메모</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.key}>
                  <td style={{ whiteSpace: "nowrap" }}>{r.kind}</td>
                  <td>{r.target}</td>
                  <td style={{ maxWidth: 280 }}>{r.content || <span className="muted">-</span>}</td>
                  <td style={{ whiteSpace: "nowrap" }}>{new Date(r.created).toLocaleDateString()}</td>
                  <td><span className={`badge ${STATUS_BADGE[r.status] ?? ""}`}>{r.result}</span></td>
                  <td>{r.note ?? <span className="muted">-</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

type ApprovalKind = "all" | "permission" | "domain" | "download";

/** 요청 > 승인 처리: 내가 승인할 수 있는 신청을 한 화면에서. 관리자는 기능 권한·도메인 열람까지, 그 밖에는 우리 가이드에 들어온 가이드 받기. */
export function ApprovalsPage() {
  const { me } = useAuth();
  const isAdmin = me?.role === "platform_admin";
  const [params, setParams] = useSearchParams();
  const tabs: [ApprovalKind, string][] = isAdmin
    ? [["all", "전체"], ["permission", "기능 권한"], ["domain", "도메인 열람"], ["download", "가이드 받기"]]
    : [["download", "가이드 받기"]];
  const asked = params.get("kind") as ApprovalKind | null;
  const tab: ApprovalKind = tabs.some(([k]) => k === asked) ? asked! : tabs[0][0];
  const show = (k: ApprovalKind) => tab === "all" || tab === k;

  return (
    <>
      <div className="page-header">
        <h1>승인 처리</h1>
        <p className="muted">
          {isAdmin
            ? "사용자가 보낸 기능 권한·도메인 열람 신청과, 우리 가이드에 들어온 가이드 받기 신청을 승인하거나 반려합니다."
            : "다른 파트너사가 우리 가이드를 받겠다고 보낸 신청을 승인하거나 거절합니다. 파트너 관리자와 그 가이드를 올린 사람이 처리할 수 있습니다."}
        </p>
      </div>
      {tabs.length > 1 && (
        <div className="filters">
          {tabs.map(([k, label]) => (
            <button key={k} className={tab === k ? "active" : ""} onClick={() => setParams(k === "all" ? {} : { kind: k })}>{label}</button>
          ))}
        </div>
      )}
      <div className="approval-list">
        {isAdmin && show("permission") && <AdminPermissionRequests />}
        {isAdmin && show("domain") && <AccessRequests />}
        {show("download") && <DownloadRequestsPanel kind="incoming" />}
      </div>
    </>
  );
}
