import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, download } from "../api";
import { useAuth } from "../auth";
import { productLabel } from "../ProductSelect";
import type { DocumentSummary } from "../types";
import { DocumentTable } from "./DocumentsPage";
import { FORMAT_LABELS } from "./GeneratePages";

interface Template {
  id: number;
  name: string;
  file_name: string;
  file_ext: "docx" | "xlsx";
  partner_name: string | null;
  uploaded_by_name: string;
  updated_at: string;
}
interface Items {
  columns: string[];
  rows: string[][];
}
interface EditableItems extends Items {
  checked: boolean[];
}
type Picked = { id: number; title: string | null };
/** 견적서 상단: B1 회사명 · J1 주소 · J2 연락처 · B2 담당자 줄(부서/ 이름 / 전화 / 메일) */
type Author = { name: string; company: string; department: string; email: string; phone: string; address: string; contact: string };
type PurchaseMeta = { quote_number?: string; date_quoted?: string; end_user?: string; partner?: string; quote_total?: string };
/** 매입 견적 PDF 한 건 = 견적서 한 행 */
interface Purchase {
  doc: Picked;
  meta: PurchaseMeta;
  columns: string[];
  rows: string[][];
  included: boolean[]; // 금액(N)에 넣을 라인
  main: number; // 대표 라인 (품명·설명·시리얼·수량·계약 번호)
  mainTouched?: boolean;
}
type Settings = { exchange_rate: string; multiplier: string; mode: "target" | "discount"; target_total: string; discount_pct: string };
interface Line {
  no: number;
  quote_number: string;
  product_number: string;
  product_name: string;
  description: string;
  quantity: number;
  note: string;
  cost_usd: number;
  amount: number;
  discount: number;
  supply: number;
  cost_krw: number;
  gp: number;
  gp_rate: number;
}
interface Totals {
  amount: number;
  discount: number;
  supply: number;
  vat_included: number;
  cost_krw: number;
  gp: number;
  gp_rate: number;
}
interface GeneratedQuote {
  id: number;
  title: string;
  version: number;
  root_id: number;
  formats: string[];
  fields: {
    title?: string;
    recipient?: string;
    date?: string;
    template_id?: number | null;
    template_name?: string | null;
    price_list_id?: number | null;
    price?: Items;
    purchases?: { document_id: number; meta: PurchaseMeta; rows: string[][]; included: boolean[]; main: number }[];
    author?: Partial<Author>;
    settings?: { exchange_rate?: number; multiplier?: number; discount_pct?: number; target_total?: number | null };
  };
  attachments: { kind: "price_list" | "purchase"; document_id: number; title: string | null }[];
  created_at: string;
}

const STEPS = ["견적서 양식", "제품 가격표 선택", "가격표 항목", "매입 견적 선택", "매입 라인 확인", "작성자 정보", "최종 확인·생성"];
const AUTHOR_FIELDS: { key: keyof Author; label: string; placeholder?: string }[] = [
  { key: "company", label: "회사명 (B1)", placeholder: "예: 주식회사 ○○ (○○ Corp.)" },
  { key: "address", label: "회사 주소 (J1)", placeholder: "예: [우편번호] 주소" },
  { key: "contact", label: "회사 연락처 (J2)", placeholder: "예: Tel : 02-0000-0000  Fax : 02-0000-0000" },
  { key: "department", label: "부서" },
  { key: "name", label: "작성자" },
  { key: "phone", label: "전화번호" },
  { key: "email", label: "이메일" },
];
// 회사명·주소·연락처는 견적서마다 같으므로 이 브라우저에 기억해 두고 다음에 채운다
const COMPANY_KEY = "quote-company-info";
function savedCompany(): Partial<Author> {
  try {
    return JSON.parse(localStorage.getItem(COMPANY_KEY) ?? "{}");
  } catch {
    return {};
  }
}
function saveCompany(a: Author) {
  try {
    localStorage.setItem(COMPANY_KEY, JSON.stringify({ company: a.company, address: a.address, contact: a.contact }));
  } catch {
    /* 저장 못 해도 견적서 작성에는 지장 없음 */
  }
}
type ImportTab = "template" | "registered" | "price_list" | "purchase" | "generated";
const IMPORT_TABS: { key: ImportTab; label: string }[] = [
  { key: "template", label: "견적서 양식" },
  { key: "registered", label: "등록한 견적서" },
  { key: "price_list", label: "제품 가격표" },
  { key: "purchase", label: "매입 금액" },
  { key: "generated", label: "생성한 견적서" },
];
// 단계마다 가져오기에서 열어 둘 탭
const STEP_TAB: Record<number, ImportTab> = { 1: "template", 2: "price_list", 4: "purchase" };
/** thales_pdf.PURCHASE_COLUMNS 와 같은 순서 */
const PURCHASE_COLUMNS = ["라인", "유지보수 제품 번호", "서비스", "대상 제품 번호", "대상 제품", "시리얼 번호", "계약 번호", "시작일", "종료일", "커버리지", "수량", "단가(USD)", "합계(USD)"];
const COL = {
  covered: "대상 제품 번호",
  coveredDesc: "대상 제품",
  qty: "수량",
  total: "합계(USD)",
  service: "서비스",
};
const won = (n: number) => `${Math.round(n).toLocaleString()}원`;
const usd = (n: number) => `USD ${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const today = () => new Date(Date.now() - new Date().getTimezoneOffset() * 60000).toISOString().slice(0, 10);
const cell = (p: { columns: string[] }, row: string[], name: string) => row[p.columns.indexOf(name)] ?? "";

/** 대표 라인 기본값: 여러 매입 견적에 공통으로 나오는 대상 제품(예: S750) 중 수량이 큰 라인 (견적서_매핑정리 2절 품목 4). */
function withDefaultMains(list: Purchase[]): Purchase[] {
  const count: Record<string, number> = {};
  for (const p of list) for (const part of new Set(p.rows.map((r) => cell(p, r, COL.covered)))) count[part] = (count[part] ?? 0) + 1;
  return list.map((p) => {
    if (p.mainTouched || !p.rows.length) return p;
    let best = 0;
    p.rows.forEach((r, i) => {
      const key = (x: string[]) => [count[cell(p, x, COL.covered)] ?? 0, Number(cell(p, x, COL.qty)) || 0];
      const [a1, a2] = key(r);
      const [b1, b2] = key(p.rows[best]);
      if (a1 > b1 || (a1 === b1 && a2 > b2)) best = i;
    });
    return { ...p, main: best };
  });
}

/** 프로젝트명 기본값: '[최종 고객] 제품 ○식 외 Renewal License 공급 건' (매핑 6절: 16식 = 수량 합계) */
function defaultTitle(list: Purchase[]): string {
  if (!list.length) return "";
  const mains = list.map((p) => p.rows[p.main] ?? p.rows[0]).filter(Boolean);
  if (!mains.length) return "";
  const p0 = list[0];
  const head = cell(p0, mains[0], COL.coveredDesc).split("(")[0].trim().toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()).replace(/\bHsm\b/g, "HSM");
  const qty = list.reduce((sum, p) => sum + (Number(cell(p, p.rows[p.main] ?? [], COL.qty)) || 0), 0);
  const parts = new Set(list.flatMap((p) => p.rows.map((r) => cell(p, r, COL.covered))));
  const renewal = mains.some((r) => /maintenance/i.test(cell(p0, r, COL.service)));
  return `[${p0.meta.end_user ?? ""}] ${head} ${qty}식${parts.size > 1 ? " 외" : ""} ${renewal ? "Renewal License " : ""}공급 건`;
}

/** 견적서 생성: 가져오기(양식·등록한 견적서·제품 가격표·매입 금액·생성한 견적서)와 7단계 작성.
 *  견적서 한 행 = 매입 견적 PDF 한 건 (견적서_매핑정리.md). 최종 확인 뒤에 앞 단계를 고치면 바로 최종 확인으로 돌아온다. */
export default function QuoteBuilderPage() {
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const fromId = Number(params.get("from")) || null;

  const [step, setStep] = useState(1);
  const [reviewed, setReviewed] = useState(false);
  const [tab, setTab] = useState<ImportTab>("template");
  const [template, setTemplate] = useState<Template | null>(null);
  const [templateChosen, setTemplateChosen] = useState(false);
  const [priceDoc, setPriceDoc] = useState<Picked | null>(null);
  const [price, setPrice] = useState<EditableItems | null>(null);
  const [priceSkipped, setPriceSkipped] = useState(false);
  const [purchases, setPurchases] = useState<Purchase[]>([]);
  const [author, setAuthor] = useState<Author>({ name: "", company: "", department: "", email: "", phone: "", address: "", contact: "" });
  const [title, setTitle] = useState("");
  const [titleTouched, setTitleTouched] = useState(false);
  const [recipient, setRecipient] = useState("");
  const [date, setDate] = useState(today());
  const [settings, setSettings] = useState<Settings>({ exchange_rate: "1360", multiplier: "2.3", mode: "target", target_total: "", discount_pct: "0" });
  const [basedOn, setBasedOn] = useState<GeneratedQuote | null>(null);
  const [created, setCreated] = useState<GeneratedQuote | null>(null);
  const [error, setError] = useState<string | null>(null);
  const templates = useQuery({ queryKey: ["quote-templates"], queryFn: () => api<Template[]>("/quote-templates") });

  // 6단계: 로그인한 사용자 정보로 작성자 칸을 채운다
  useEffect(() => {
    if (me && !author.name) {
      const saved = savedCompany();
      setAuthor({
        name: me.name,
        company: saved.company || me.partner_name || me.company_name || "",
        address: saved.address ?? "",
        contact: saved.contact ?? "",
        department: me.department ?? "",
        email: me.email,
        phone: me.phone ?? "",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me]);
  useEffect(() => {
    if (STEP_TAB[step]) setTab(STEP_TAB[step]);
  }, [step]);
  // 매입 견적이 바뀌면 수신처(Primary Partner)·프로젝트명 기본값을 채운다 (직접 고쳤으면 그대로)
  useEffect(() => {
    if (!recipient && purchases[0]?.meta.partner) setRecipient(purchases[0].meta.partner);
    if (!titleTouched) setTitle(defaultTitle(purchases));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [purchases]);

  const go = (n: number) => {
    setError(null);
    setStep(n);
    if (n === 7) setReviewed(true);
  };
  const next = () => go(reviewed ? 7 : step + 1);

  const pickTemplate = (t: Template | null) => {
    setTemplate(t);
    setTemplateChosen(true);
  };
  const pickPrice = async (d: Picked) => {
    if (priceDoc?.id === d.id) return;
    setPriceDoc(d);
    setPrice(null);
    setPriceSkipped(false);
    try {
      const items = await api<Items>(`/documents/${d.id}/items`);
      setPrice({ ...items, checked: items.rows.map(() => false) });
    } catch (e) {
      setError((e as Error).message);
    }
  };
  // 4단계: 매입 견적은 여러 건을 고른다 (한 건 = 견적서 한 행)
  const togglePurchase = async (d: Picked) => {
    if (purchases.some((p) => p.doc.id === d.id)) {
      setPurchases((list) => withDefaultMains(list.filter((p) => p.doc.id !== d.id)));
      return;
    }
    try {
      const items = await api<Items & { meta?: PurchaseMeta }>(`/documents/${d.id}/items`);
      setPurchases((list) =>
        withDefaultMains([...list, { doc: d, meta: items.meta ?? {}, columns: items.columns, rows: items.rows, included: items.rows.map(() => true), main: 0 }]),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  };

  // 생성한 견적서를 불러와 고친다 → 최종 확인 단계에서 시작, 생성하면 다음 버전
  const loadGenerated = (g: GeneratedQuote) => {
    const f = g.fields;
    setTemplate(templates.data?.find((t) => t.id === f.template_id) ?? null);
    setTemplateChosen(true);
    const titleOf = (id: number) => g.attachments.find((a) => a.document_id === id)?.title ?? null;
    if (f.price_list_id) {
      setPriceDoc({ id: f.price_list_id, title: titleOf(f.price_list_id) });
      setPrice(f.price ? { ...f.price, checked: f.price.rows.map(() => true) } : null);
    } else {
      setPriceDoc(null);
      setPrice(null);
      setPriceSkipped(true);
    }
    setPurchases(
      (f.purchases ?? []).map((p) => ({
        doc: { id: p.document_id, title: titleOf(p.document_id) },
        meta: p.meta,
        columns: PURCHASE_COLUMNS,
        rows: p.rows,
        included: p.included,
        main: p.main,
        mainTouched: true,
      })),
    );
    if (f.author) setAuthor((a) => ({ ...a, ...f.author }));
    setTitle(f.title ?? g.title);
    setTitleTouched(true);
    setRecipient(f.recipient ?? "");
    setDate(f.date ?? today());
    const s = f.settings ?? {};
    setSettings({
      exchange_rate: String(s.exchange_rate ?? 1360),
      multiplier: String(s.multiplier ?? 2.3),
      mode: s.target_total ? "target" : "discount",
      target_total: s.target_total ? String(s.target_total) : "",
      discount_pct: String(s.discount_pct ?? 0),
    });
    setBasedOn(g);
    setCreated(null);
    go(7);
  };
  const loaded = useRef(false);
  useEffect(() => {
    if (fromId && templates.data && !loaded.current) {
      loaded.current = true;
      api<GeneratedQuote>(`/generated/${fromId}`).then(loadGenerated, (e: Error) => setError(e.message));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fromId, templates.data]);

  const body = () => ({
    title,
    recipient,
    date,
    template_id: template?.id ?? null,
    price_list_id: priceDoc?.id ?? null,
    price: price ? { columns: price.columns, rows: price.rows.filter((_, i) => price.checked[i]) } : { columns: [], rows: [] },
    purchases: purchases.map((p) => ({ document_id: p.doc.id, meta: p.meta, rows: p.rows, included: p.included, main: p.main })),
    author,
    settings: {
      exchange_rate: Number(settings.exchange_rate) || 0,
      multiplier: Number(settings.multiplier) || 0,
      discount_pct: settings.mode === "discount" ? Number(settings.discount_pct) || 0 : 0,
      target_total: settings.mode === "target" && Number(settings.target_total) > 0 ? Number(settings.target_total) : null,
    },
    based_on_id: basedOn?.id ?? null,
  });

  const stepOk: Record<number, boolean> = {
    1: templateChosen,
    2: !!priceDoc || priceSkipped, // 가격표는 참고용이라 건너뛸 수 있다
    3: priceSkipped || (!!price && price.checked.some(Boolean)),
    4: purchases.length > 0,
    5: purchases.length > 0 && purchases.every((p) => p.included.some(Boolean)),
    6: !!author.name.trim(),
    7: !!title.trim() && !!recipient.trim() && Number(settings.exchange_rate) > 0 && Number(settings.multiplier) > 0,
  };
  const stepHint: Record<number, string> = {
    1: "위 '가져오기 > 견적서 양식'에서 양식을 고르세요. 기본 양식은 유니포인트 견적서 엑셀입니다.",
    2: "위 '가져오기 > 제품 가격표'에서 가격표를 고르세요. 가격표는 품명·리스트가 참고용이라 견적 금액 계산에는 쓰지 않습니다(건너뛸 수 있음).",
    3: "참고할 제품을 체크하세요. 검색으로 제품 번호·이름을 찾을 수 있습니다.",
    4: "위 '가져오기 > 매입 금액'에서 이번 견적에 넣을 매입 견적(Thales 견적서 PDF)을 모두 체크하세요. 한 건이 견적서 한 행이 됩니다.",
    5: "매입 견적마다 금액에 넣을 라인(포함)과 견적서에 보일 대표 라인을 고르세요. 값이 다르면(예: 기간이 PDF에 없을 때) 칸을 눌러 고치세요.",
    6: "견적서 상단의 회사명·주소·연락처와 담당자 줄(부서/ 이름 / 전화 / 메일)에 들어갑니다. 이름·부서·전화·메일은 로그인한 사용자 정보로, 회사 정보는 지난번 입력값으로 채웠습니다.",
    7: "수신처·프로젝트명·환율·목표 금액을 확인하고 미리보기를 본 뒤 생성하세요. 고칠 곳이 있으면 위 단계 번호를 누르세요.",
  };

  return (
    <>
      <div className="page-header">
        <h1>견적서 생성</h1>
        <p className="muted">
          가져오기에서 견적서 양식·제품 가격표·매입 견적을 고르고, 아래 순서대로 확인해 견적서(엑셀)를 만듭니다. 만든 견적서는 <Link to="/quotes/created">생성한 견적서</Link>에서 이력과 함께 봅니다.
        </p>
      </div>

      <section className="card">
        <h2 className="section-title">가져오기</h2>
        <div className="filters">
          {IMPORT_TABS.map((t) => (
            <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
              {t.label}
              {t.key === "purchase" && purchases.length ? ` ${purchases.length}건 ✓` : ""}
              {(t.key === "template" && templateChosen) || (t.key === "price_list" && priceDoc) ? " ✓" : ""}
            </button>
          ))}
        </div>
        {tab === "template" && <TemplatesPanel selected={templateChosen ? template?.id ?? 0 : null} onPick={pickTemplate} />}
        {tab === "registered" && (
          <>
            <p className="muted">문서 등록에서 올린 견적서입니다. 참고용으로 열어 보거나 내려받을 수 있습니다.</p>
            <DocumentTable query="doc_type=quote" showStatus={false} />
          </>
        )}
        {tab === "price_list" && <DocPicker docType="price_list" checked={priceDoc ? [priceDoc.id] : []} onPick={pickPrice} />}
        {tab === "purchase" && <DocPicker docType="purchase" multiple checked={purchases.map((p) => p.doc.id)} onPick={togglePurchase} />}
        {tab === "generated" && <GeneratedPicker checked={basedOn?.id ?? null} onPick={loadGenerated} />}
      </section>

      <section className="card">
        <ol className="stepper">
          {STEPS.map((label, i) => {
            const n = i + 1;
            return (
              <li key={n} className={`${n === step ? "current" : ""} ${stepOk[n] ? "done" : ""}`}>
                <button disabled={!(reviewed || n <= step)} onClick={() => go(n)} title={reviewed ? "이 단계로 돌아가 고치면 바로 최종 확인으로 돌아옵니다" : undefined}>
                  <span className="step-no">{n}</span> {label}
                </button>
              </li>
            );
          })}
        </ol>
        <h2 className="section-title">({step}) {STEPS[step - 1]}</h2>
        <p className="muted">{stepHint[step]}</p>

        {step === 1 && (
          <p>
            선택한 양식: <strong>{templateChosen ? (template ? `${template.name} (${template.file_ext === "docx" ? "Word" : "Excel"})` : "기본 양식 (유니포인트 견적서 엑셀)") : "아직 고르지 않음"}</strong>
          </p>
        )}
        {step === 2 && (
          <div className="actions" style={{ alignItems: "center" }}>
            <span>선택한 가격표: <strong>{priceDoc ? priceDoc.title ?? "(제목 없음)" : priceSkipped ? "건너뜀" : "아직 고르지 않음"}</strong></span>
            {!priceDoc && !priceSkipped && <button className="link" onClick={() => setPriceSkipped(true)}>가격표 없이 진행</button>}
          </div>
        )}
        {step === 3 && (priceSkipped ? <p className="muted">가격표를 건너뛰었습니다.</p> : <PriceEditor items={price} onChange={setPrice} />)}
        {step === 4 && (
          <p>
            선택한 매입 견적: <strong>{purchases.length ? purchases.map((p) => p.meta.quote_number || p.doc.title).join(", ") : "아직 고르지 않음"}</strong>
          </p>
        )}
        {step === 5 && (
          <PurchaseEditor
            purchases={purchases}
            onChange={(i, p) => setPurchases((list) => list.map((x, j) => (j === i ? p : x)))}
          />
        )}
        {step === 6 && (
          <div className="form-row">
            {AUTHOR_FIELDS.map((f) => (
              <label key={f.key} style={["company", "address", "contact"].includes(f.key) ? { flex: "1 1 320px" } : undefined}>
                {f.label}
                {f.key === "name" && <span className="required"> *</span>}
                <input
                  value={author[f.key]}
                  placeholder={f.placeholder}
                  onChange={(e) => {
                    const next = { ...author, [f.key]: e.target.value };
                    setAuthor(next);
                    if (["company", "address", "contact"].includes(f.key)) saveCompany(next);
                  }}
                />
              </label>
            ))}
          </div>
        )}
        {step === 7 && (
          <FinalStep
            fields={{ title, recipient, date, settings }}
            setTitle={(v) => {
              setTitle(v);
              setTitleTouched(true);
            }}
            setRecipient={setRecipient}
            setDate={setDate}
            setSettings={setSettings}
            template={templateChosen ? template : undefined}
            priceDoc={priceDoc}
            purchases={purchases}
            author={author}
            body={body}
            ready={[1, 2, 3, 4, 5, 6, 7].every((n) => stepOk[n])}
            missing={[1, 2, 3, 4, 5, 6, 7].filter((n) => !stepOk[n]).map((n) => STEPS[n - 1])}
            basedOn={basedOn}
            created={created}
            onCreated={(g) => {
              setCreated(g);
              setBasedOn(g); // 오류가 있어 고쳐 다시 만들면 다음 버전
              queryClient.invalidateQueries({ queryKey: ["generated", "quote"] });
            }}
            goStep={go}
          />
        )}
        {error && <p className="error">{error}</p>}
        {step < 7 && (
          <div className="actions" style={{ marginTop: 14 }}>
            {step > 1 && !reviewed && <button onClick={() => go(step - 1)}>이전</button>}
            <button className="primary" disabled={!stepOk[step]} onClick={next}>
              {reviewed ? "최종 확인으로" : "다음"}
            </button>
          </div>
        )}
      </section>
    </>
  );
}

/** 가져오기 > 견적서 양식: 조직의 양식을 등록·변경·삭제하고, 견적서에 쓸 양식을 하나 고른다. */
function TemplatesPanel({ selected, onPick }: { selected: number | null; onPick: (t: Template | null) => void }) {
  const queryClient = useQueryClient();
  const templates = useQuery({ queryKey: ["quote-templates"], queryFn: () => api<Template[]>("/quote-templates") });
  const [name, setName] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [inputKey, setInputKey] = useState(0);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["quote-templates"] });
  const add = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append("name", name || (file?.name.replace(/\.[^.]+$/, "") ?? "견적서 양식"));
      if (file) form.append("file", file);
      return api<Template>("/quote-templates", { method: "POST", body: form });
    },
    onSuccess: (t) => {
      setName("");
      setFile(null);
      setInputKey((k) => k + 1);
      refresh();
      onPick(t);
    },
  });
  const replace = useMutation({
    mutationFn: ({ id, f }: { id: number; f: File }) => {
      const form = new FormData();
      form.append("file", f);
      return api<Template>(`/quote-templates/${id}`, { method: "PUT", body: form });
    },
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: number) => api(`/quote-templates/${id}`, { method: "DELETE" }),
    onSuccess: (_d, id) => {
      refresh();
      if (selected === id) onPick(null);
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    add.mutate();
  };

  return (
    <>
      <p className="muted">
        기본 양식은 유니포인트 견적서 엑셀입니다. 직접 올리는 양식(Word·Excel)에는 <code>{"{{제목}}"}</code> <code>{"{{작성자}}"}</code> <code>{"{{소속}}"}</code>{" "}
        <code>{"{{부서}}"}</code> <code>{"{{이메일}}"}</code> <code>{"{{전화번호}}"}</code> <code>{"{{작성일}}"}</code> 를 적어 두면 그 자리에 값이 들어가고,{" "}
        <code>{"{{품목표}}"}</code> 자리에는 견적 품목 표가 들어갑니다(없으면 문서 끝에 붙음).
      </p>
      <div className="table-wrap">
        <table style={{ minWidth: 760 }}>
          <thead><tr><th style={{ width: 48 }}>선택</th><th>양식 이름</th><th>파일</th><th>올린 사람</th><th>변경 일시</th><th>관리</th></tr></thead>
          <tbody>
            <tr className={selected === 0 ? "highlight" : ""}>
              <td><input type="radio" name="quote-template" checked={selected === 0} onChange={() => onPick(null)} aria-label="기본 양식" /></td>
              <td>기본 양식</td>
              <td className="muted">유니포인트 견적서 엑셀 (견적서_매핑정리 기준, 엑셀·PDF)</td>
              <td>-</td><td>-</td><td>-</td>
            </tr>
            {templates.data?.map((t) => (
              <tr key={t.id} className={selected === t.id ? "highlight" : ""}>
                <td><input type="radio" name="quote-template" checked={selected === t.id} onChange={() => onPick(t)} aria-label={`${t.name} 선택`} /></td>
                <td>{t.name}</td>
                <td>{t.file_name}</td>
                <td>{t.uploaded_by_name}</td>
                <td style={{ whiteSpace: "nowrap" }}>{new Date(t.updated_at).toLocaleString()}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  <div className="actions">
                    <button className="link" onClick={() => download(`/quote-templates/${t.id}/download`)}>받기</button>
                    <label className="link" style={{ cursor: "pointer" }}>
                      파일 변경
                      <input
                        type="file"
                        accept=".docx,.xlsx"
                        hidden
                        onChange={(e) => {
                          const f = e.target.files?.[0];
                          if (f) replace.mutate({ id: t.id, f });
                          e.target.value = "";
                        }}
                      />
                    </label>
                    <button
                      className="link danger-link"
                      onClick={() => window.confirm(`'${t.name}' 양식을 삭제할까요?`) && remove.mutate(t.id)}
                    >
                      삭제
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(add.error || replace.error || remove.error) && <p className="error">{(add.error ?? replace.error ?? remove.error)!.message}</p>}
      <form className="form-row" style={{ marginTop: 12, alignItems: "flex-end" }} onSubmit={submit}>
        <label style={{ flex: "0 0 240px" }}>
          새 양식 이름
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="비우면 파일 이름" />
        </label>
        <label>
          양식 파일 (Word .docx · Excel .xlsx)
          <input key={inputKey} type="file" accept=".docx,.xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} required />
        </label>
        <div><button className="primary" disabled={add.isPending || !file}>{add.isPending ? "올리는 중…" : "양식 등록"}</button></div>
      </form>
    </>
  );
}


/** 가져오기 > 제품 가격표 · 매입 금액: 문서 등록에서 올린 문서를 고른다 (매입 견적은 여러 건). */
function DocPicker({ docType, checked, onPick, multiple = false }: { docType: "price_list" | "purchase"; checked: number[]; onPick: (d: Picked) => void; multiple?: boolean }) {
  const label = docType === "price_list" ? "제품 가격표" : "매입 금액";
  const docs = useQuery({ queryKey: ["documents", `doc_type=${docType}`], queryFn: () => api<DocumentSummary[]>(`/documents?doc_type=${docType}`) });
  if (docs.isLoading) return <p className="muted">불러오는 중…</p>;
  if (docs.error) return <p className="error">{docs.error.message}</p>;
  if (!docs.data?.length) return <p className="muted">등록한 {label}가 없습니다. <Link to={`/documents?type=${docType}`}>문서 등록</Link>에서 {label}(으)로 올리세요.</p>;
  return (
    <div className="table-wrap">
      <table style={{ minWidth: 700 }}>
        <thead><tr><th style={{ width: 48 }}>선택</th><th>문서 이름</th><th>벤더</th><th>제품</th><th>형식</th><th>등록자</th><th>등록 일자</th></tr></thead>
        <tbody>
          {docs.data.map((d) => (
            <tr key={d.id} className={checked.includes(d.id) ? "highlight" : ""}>
              <td>
                <input
                  type={multiple ? "checkbox" : "radio"}
                  name={`pick-${docType}`}
                  checked={checked.includes(d.id)}
                  onChange={() => onPick({ id: d.id, title: d.title })}
                  aria-label={`${d.title ?? "문서"} 선택`}
                />
              </td>
              <td>{d.title ?? `문서 ${d.id}`}</td>
              <td>{d.vendor_name}</td>
              <td>{productLabel(d.product, d.product_detail)}</td>
              <td>{d.source_type.toUpperCase()}</td>
              <td>{d.uploaded_by_name ?? "-"}</td>
              <td style={{ whiteSpace: "nowrap" }}>{new Date(d.created_at).toLocaleDateString()}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** 3단계: 가격표 항목(제품 번호·제품명·설명·리스트 가격)을 체크한다. 가격표는 행이 많아 검색을 둔다. */
function PriceEditor({ items, onChange }: { items: EditableItems | null; onChange: (v: EditableItems) => void }) {
  const [q, setQ] = useState("");
  if (!items) return <p className="muted">제품 가격표를 먼저 고르세요.</p>;
  if (!items.rows.length) return <p className="muted">이 문서에서 가격표 항목을 찾지 못했습니다.</p>;
  const keyword = q.trim().toLowerCase();
  const shown = items.rows.map((r, i) => [r, i] as const).filter(([r]) => !keyword || r.join(" ").toLowerCase().includes(keyword));
  const toggle = (i: number) => onChange({ ...items, checked: items.checked.map((x, j) => (j === i ? !x : x)) });
  return (
    <>
      <div className="form-row" style={{ alignItems: "flex-end" }}>
        <label style={{ flex: "0 0 320px" }}>
          검색 (제품 번호·이름·설명)
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="예: S750, 908-000364" />
        </label>
        <span className="muted">{items.checked.filter(Boolean).length}개 체크 · 전체 {items.rows.length}개</span>
      </div>
      <div className="table-wrap" style={{ maxHeight: 420 }}>
        <table style={{ minWidth: 760 }}>
          <thead><tr><th style={{ width: 48 }}>선택</th>{items.columns.map((c) => <th key={c}>{c}</th>)}</tr></thead>
          <tbody>
            {shown.map(([r, i]) => (
              <tr key={i} className={items.checked[i] ? "highlight" : ""}>
                <td><input type="checkbox" checked={items.checked[i]} onChange={() => toggle(i)} aria-label={`${r[0]} 선택`} /></td>
                {r.map((v, j) => <td key={j}>{v}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/** 5단계: 매입 견적마다 금액에 넣을 라인(포함)과 견적서에 보일 대표 라인을 고르고, 값을 고친다. */
function PurchaseEditor({ purchases, onChange }: { purchases: Purchase[]; onChange: (i: number, p: Purchase) => void }) {
  if (!purchases.length) return <p className="muted">매입 견적을 먼저 고르세요.</p>;
  // 화면에 보일 열 (라인 번호·서비스·대상 제품 번호는 대표 라인 판단에만 쓰므로 좁게)
  const visible = ["라인", "대상 제품", "시리얼 번호", "계약 번호", "시작일", "종료일", "커버리지", "수량", "단가(USD)", "합계(USD)"];
  return (
    <>
      {purchases.map((p, pi) => {
        const cols = visible.filter((c) => p.columns.includes(c));
        const total = p.rows.reduce((sum, r, i) => sum + (p.included[i] ? Number(cell(p, r, COL.total)) || 0 : 0), 0);
        const set = (r: number, name: string, v: string) =>
          onChange(pi, { ...p, rows: p.rows.map((row, i) => (i === r ? row.map((x, j) => (j === p.columns.indexOf(name) ? v : x)) : row)) });
        return (
          <div key={p.doc.id} className="review-block">
            <div className="summary-head">
              <strong>
                {pi + 1}행 · {p.meta.quote_number || p.doc.title} {p.meta.end_user ? `· ${p.meta.end_user}` : ""} {p.meta.partner ? `· ${p.meta.partner}` : ""}
              </strong>
              <span className="muted">
                매입(N) {usd(total)}
                {p.meta.quote_total ? ` / Quote Total ${usd(Number(p.meta.quote_total))}` : ""}
              </span>
            </div>
            {!p.columns.includes(COL.total) && <p className="error">Thales 매입 견적 형식이 아니어서 라인을 알아보지 못했습니다.</p>}
            <div className="table-wrap">
              <table className="items-table" style={{ minWidth: 1100 }}>
                <thead>
                  <tr><th style={{ width: 48 }}>포함</th><th style={{ width: 48 }}>대표</th>{cols.map((c) => <th key={c}>{c}</th>)}</tr>
                </thead>
                <tbody>
                  {p.rows.map((r, i) => (
                    <tr key={i} className={p.main === i ? "highlight" : ""}>
                      <td>
                        <input
                          type="checkbox"
                          checked={p.included[i]}
                          onChange={() => onChange(pi, { ...p, included: p.included.map((x, j) => (j === i ? !x : x)) })}
                          aria-label={`${i + 1}번 라인 금액 포함`}
                        />
                      </td>
                      <td>
                        <input type="radio" name={`main-${p.doc.id}`} checked={p.main === i} onChange={() => onChange(pi, { ...p, main: i, mainTouched: true })} aria-label={`${i + 1}번 라인 대표`} />
                      </td>
                      {cols.map((c) => (
                        <td key={c} style={c === "대상 제품" ? { minWidth: 260 } : undefined}>
                          {c === "라인" ? cell(p, r, c) : <input className="cell-input" value={cell(p, r, c)} onChange={(e) => set(i, c, e.target.value)} aria-label={`${i + 1}번 라인 ${c}`} />}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        );
      })}
    </>
  );
}

/** 7단계: 수신처·프로젝트명·견적일자·환율·목표 금액 확인 → 미리보기 → 형식 골라 생성. 미리보기 뒤 내용을 바꾸면 다시 미리보기. */
function FinalStep(props: {
  fields: { title: string; recipient: string; date: string; settings: Settings };
  setTitle: (v: string) => void;
  setRecipient: (v: string) => void;
  setDate: (v: string) => void;
  setSettings: (v: Settings) => void;
  template: Template | null | undefined;
  priceDoc: Picked | null;
  purchases: Purchase[];
  author: Author;
  body: () => object;
  ready: boolean;
  missing: string[];
  basedOn: GeneratedQuote | null;
  created: GeneratedQuote | null;
  onCreated: (g: GeneratedQuote) => void;
  goStep: (n: number) => void;
}) {
  const { template, created, fields } = props;
  const s = fields.settings;
  const [preview, setPreview] = useState<{ html: string; formats: string[]; lines: Line[]; totals: Totals; key: string } | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [format, setFormat] = useState("xlsx");
  const key = JSON.stringify(props.body());
  const previewed = preview?.key === key;
  const runPreview = useMutation({
    mutationFn: () => api<{ html: string; formats: string[]; lines: Line[]; totals: Totals }>("/quote-builder/preview", { method: "POST", json: props.body() }),
    onSuccess: (r) => {
      setPreview({ ...r, key });
      setFormat((f) => (r.formats.includes(f) ? f : r.formats[0]));
      setShowPreview(true);
    },
  });
  const create = useMutation({
    mutationFn: () => api<GeneratedQuote>("/quote-builder", { method: "POST", json: props.body() }),
    onSuccess: async (g) => {
      props.onCreated(g);
      setShowPreview(false);
      await download(`/generated/${g.id}/download?format=${format}`);
    },
  });
  const block = (n: number, label: string, children: ReactNode) => (
    <div className="review-block">
      <div className="summary-head">
        <strong>({n}) {label}</strong>
        <button className="link" onClick={() => props.goStep(n)}>수정</button>
      </div>
      {children}
    </div>
  );

  return (
    <>
      <div className="form-row">
        <label style={{ flex: "1 1 420px" }}>
          프로젝트명 (B8) <span className="required">*</span>
          <input value={fields.title} onChange={(e) => props.setTitle(e.target.value)} />
        </label>
        <label style={{ flex: "0 0 220px" }}>
          수신처 (B7 ○○ 귀중) <span className="required">*</span>
          <input value={fields.recipient} onChange={(e) => props.setRecipient(e.target.value)} placeholder="예: 파트너사명" />
        </label>
        <label style={{ flex: "0 0 170px" }}>
          견적일자 (H8)
          <input type="date" value={fields.date} onChange={(e) => props.setDate(e.target.value)} />
        </label>
      </div>
      <div className="form-row">
        <label style={{ flex: "0 0 140px" }}>
          환율 (O열, 원/USD) <span className="required">*</span>
          <input inputMode="decimal" value={s.exchange_rate} onChange={(e) => props.setSettings({ ...s, exchange_rate: e.target.value })} />
        </label>
        <label style={{ flex: "0 0 140px" }}>
          배수 (금액 = 매입×환율×배수)
          <input inputMode="decimal" value={s.multiplier} onChange={(e) => props.setSettings({ ...s, multiplier: e.target.value })} />
        </label>
        <label style={{ flex: "0 0 200px" }}>
          할인율 정하는 방법
          <select value={s.mode} onChange={(e) => props.setSettings({ ...s, mode: e.target.value as Settings["mode"] })}>
            <option value="target">목표 공급가 합계로 역산 (P9)</option>
            <option value="discount">할인율 직접 입력</option>
          </select>
        </label>
        {s.mode === "target" ? (
          <label style={{ flex: "0 0 200px" }}>
            목표 공급가 합계 (원, 부가세 별도)
            <input inputMode="numeric" value={s.target_total} onChange={(e) => props.setSettings({ ...s, target_total: e.target.value.replace(/[^\d.]/g, "") })} placeholder="예: 163800000" />
          </label>
        ) : (
          <label style={{ flex: "0 0 140px" }}>
            할인율 (%)
            <input inputMode="decimal" value={s.discount_pct} onChange={(e) => props.setSettings({ ...s, discount_pct: e.target.value })} />
          </label>
        )}
      </div>
      {block(1, "견적서 양식", <p>{template === undefined ? "아직 고르지 않음" : template ? `${template.name} (${template.file_name})` : "기본 양식 (유니포인트 견적서 엑셀)"}</p>)}
      {block(2, "제품 가격표 (참고)", <p>{props.priceDoc?.title ?? (props.priceDoc ? "(제목 없음)" : "사용 안 함")}</p>)}
      {block(4, "매입 견적", <p>{props.purchases.map((p) => p.meta.quote_number || p.doc.title).join(", ") || "아직 고르지 않음"}</p>)}
      {block(6, "작성자 정보", <p>{AUTHOR_FIELDS.map((f) => `${f.label}: ${props.author[f.key] || "-"}`).join(" · ")}</p>)}

      {previewed && preview && (
        <div className="review-block">
          <strong>견적 품목 계산 (매입·GP 는 엑셀의 인쇄 영역 밖 칸에만 들어갑니다)</strong>
          <div className="table-wrap" style={{ marginTop: 8 }}>
            <table style={{ minWidth: 980 }}>
              <thead>
                <tr><th>No</th><th>매입 견적</th><th>Product Name</th><th>수량</th><th>매입(USD)</th><th>금액</th><th>할인율</th><th>공급가</th><th>매입(원)</th><th>GP</th><th>GP율</th></tr>
              </thead>
              <tbody>
                {preview.lines.map((l) => (
                  <tr key={l.no}>
                    <td>{l.no}</td><td>{l.quote_number}</td><td>{l.product_name}</td><td>{l.quantity}</td><td>{usd(l.cost_usd)}</td>
                    <td>{won(l.amount)}</td><td>{(l.discount * 100).toFixed(2)}%</td><td>{won(l.supply)}</td><td>{won(l.cost_krw)}</td>
                    <td>{won(l.gp)}</td><td>{(l.gp_rate * 100).toFixed(2)}%</td>
                  </tr>
                ))}
                <tr>
                  <td colSpan={5}><strong>합계</strong></td><td>{won(preview.totals.amount)}</td><td>{(preview.totals.discount * 100).toFixed(2)}%</td>
                  <td><strong>{won(preview.totals.supply)}</strong></td><td>{won(preview.totals.cost_krw)}</td><td>{won(preview.totals.gp)}</td>
                  <td>{(preview.totals.gp_rate * 100).toFixed(2)}%</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="muted">부가세 포함 {won(preview.totals.vat_included)}</p>
        </div>
      )}
      {props.basedOn && <p className="muted">'{props.basedOn.title}' v{props.basedOn.version}을(를) 고쳐 만들면 같은 견적서의 다음 버전이 됩니다.</p>}
      {!props.ready && <p className="error">아직 끝나지 않은 단계: {props.missing.join(", ")}</p>}
      {(runPreview.error || create.error) && <p className="error">{(runPreview.error ?? create.error)!.message}</p>}

      <div className="actions" style={{ marginTop: 14, alignItems: "center" }}>
        <button disabled={!props.ready || runPreview.isPending} onClick={() => runPreview.mutate()}>
          {runPreview.isPending ? "미리보기 만드는 중…" : "미리보기"}
        </button>
        {previewed && (
          <>
            <span className="muted">받을 형식</span>
            {preview!.formats.map((f) => (
              <label key={f} className="check">
                <input type="radio" name="quote-format" checked={format === f} onChange={() => setFormat(f)} /> {FORMAT_LABELS[f] ?? f}
              </label>
            ))}
            <button className="primary" disabled={create.isPending} onClick={() => create.mutate()}>
              {create.isPending ? "생성 중…" : "최종 생성"}
            </button>
          </>
        )}
        {!previewed && props.ready && <span className="muted">미리보기를 확인한 뒤 최종 생성할 수 있습니다.</span>}
      </div>

      {created && (
        <div className="notice" style={{ marginTop: 14 }}>
          <strong>'{created.title}' v{created.version}을(를) 만들었습니다.</strong>
          <div className="actions" style={{ marginTop: 8 }}>
            {created.formats.map((f) => (
              <button key={f} className="link" onClick={() => download(`/generated/${created.id}/download?format=${f}`)}>{FORMAT_LABELS[f] ?? f} 받기</button>
            ))}
            <Link to="/quotes/created">생성한 견적서 보기</Link>
          </div>
          <p className="muted" style={{ marginTop: 6 }}>잘못된 곳이 있으면 위 단계 번호나 '수정'을 눌러 고친 뒤 다시 생성하세요 (다음 버전으로 저장됩니다).</p>
        </div>
      )}

      {showPreview && preview && (
        <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && setShowPreview(false)}>
          <div className="modal preview-modal" role="dialog" aria-modal="true" aria-label="견적서 미리보기">
            <div className="summary-head">
              <h2 style={{ margin: 0 }}>견적서 미리보기{template ? ` · ${template.name}` : " · 유니포인트 견적서"}</h2>
              <button className="link" onClick={() => setShowPreview(false)}>닫기</button>
            </div>
            <iframe title="견적서 미리보기" className="preview-frame" sandbox="" srcDoc={preview.html} />
            <div className="actions" style={{ marginTop: 10 }}>
              <button onClick={() => setShowPreview(false)}>고칠 곳이 있어요</button>
              <button className="primary" disabled={create.isPending} onClick={() => create.mutate()}>
                이상 없음 · {FORMAT_LABELS[format] ?? format}(으)로 최종 생성
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/** 가져오기 > 생성한 견적서: 이전에 만든 견적서를 불러와 고쳐 다음 버전으로 만든다. */
function GeneratedPicker({ checked, onPick }: { checked: number | null; onPick: (g: GeneratedQuote) => void }) {
  const rows = useQuery({ queryKey: ["generated", "quote"], queryFn: () => api<GeneratedQuote[]>("/generated?doc_type=quote") });
  if (rows.isLoading) return <p className="muted">불러오는 중…</p>;
  if (rows.error) return <p className="error">{rows.error.message}</p>;
  if (!rows.data?.length) return <p className="muted">아직 생성한 견적서가 없습니다.</p>;
  return (
    <>
      <p className="muted">고르면 그 견적서 내용이 모두 채워지고 최종 확인 단계로 갑니다. 고쳐서 생성하면 같은 견적서의 다음 버전이 됩니다.</p>
      <div className="table-wrap">
        <table style={{ minWidth: 640 }}>
          <thead><tr><th style={{ width: 48 }}>선택</th><th>견적서 제목</th><th>버전</th><th>양식</th><th>생성 일시</th></tr></thead>
          <tbody>
            {rows.data.map((g) => (
              <tr key={g.id} className={checked === g.id ? "highlight" : ""}>
                <td><input type="radio" name="pick-generated-quote" checked={checked === g.id} onChange={() => onPick(g)} aria-label={`${g.title} v${g.version} 불러오기`} /></td>
                <td>{g.title}</td>
                <td>v{g.version}</td>
                <td>{g.fields.template_name ?? "기본 양식"}</td>
                <td style={{ whiteSpace: "nowrap" }}>{new Date(g.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
