import { useEffect, useRef, useState, type FormEvent } from "react";
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
type Author = { name: string; company: string; department: string; email: string; phone: string };
interface GeneratedQuote {
  id: number;
  title: string;
  version: number;
  root_id: number;
  formats: string[];
  fields: {
    title?: string;
    template_id?: number | null;
    template_name?: string | null;
    items?: { price_list?: Items; purchase?: Items };
    author?: Partial<Author>;
  };
  attachments: { kind: "price_list" | "purchase"; document_id: number; title: string | null }[];
  created_at: string;
}

const STEPS = ["견적서 양식", "제품 가격표 선택", "가격표 항목", "매입 금액 선택", "매입 항목", "작성자 정보", "최종 확인·생성"];
const AUTHOR_FIELDS: { key: keyof Author; label: string }[] = [
  { key: "name", label: "작성자" },
  { key: "company", label: "소속" },
  { key: "department", label: "부서" },
  { key: "email", label: "이메일" },
  { key: "phone", label: "전화번호" },
];
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

const editable = (items: Items, checked = false): EditableItems => ({ ...items, checked: items.rows.map(() => checked) });
const pickedRows = (items: EditableItems | null): Items => ({
  columns: items?.columns ?? [],
  rows: items ? items.rows.filter((_, i) => items.checked[i]) : [],
});

/** 견적서 생성: 가져오기(양식·등록한 견적서·제품 가격표·매입 금액·생성한 견적서)와 7단계 작성.
 *  최종 확인 뒤에 앞 단계를 고치면 다음 단계가 아니라 바로 최종 확인으로 돌아온다. */
export default function QuoteBuilderPage() {
  const { me } = useAuth();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const fromId = Number(params.get("from")) || null;

  const [step, setStep] = useState(1);
  const [reviewed, setReviewed] = useState(false); // 최종 확인까지 한 번 갔는지
  const [tab, setTab] = useState<ImportTab>("template");
  const [template, setTemplate] = useState<Template | null>(null);
  const [templateChosen, setTemplateChosen] = useState(false); // 기본 양식(null)도 고른 것으로 친다
  const [priceDoc, setPriceDoc] = useState<Picked | null>(null);
  const [price, setPrice] = useState<EditableItems | null>(null);
  const [purchaseDoc, setPurchaseDoc] = useState<Picked | null>(null);
  const [purchase, setPurchase] = useState<EditableItems | null>(null);
  const [author, setAuthor] = useState<Author>({ name: "", company: "", department: "", email: "", phone: "" });
  const [title, setTitle] = useState("");
  const [basedOn, setBasedOn] = useState<GeneratedQuote | null>(null);
  const [created, setCreated] = useState<GeneratedQuote | null>(null);
  const [error, setError] = useState<string | null>(null);
  const templates = useQuery({ queryKey: ["quote-templates"], queryFn: () => api<Template[]>("/quote-templates") });

  // 6단계: 로그인한 사용자 정보로 작성자 칸을 채운다
  useEffect(() => {
    if (me && !author.name)
      setAuthor({ name: me.name, company: me.partner_name ?? me.company_name ?? "", department: me.department ?? "", email: me.email, phone: me.phone ?? "" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [me]);
  useEffect(() => {
    if (STEP_TAB[step]) setTab(STEP_TAB[step]);
  }, [step]);

  const go = (n: number) => {
    setError(null);
    setStep(n);
    if (n === 7) setReviewed(true);
  };
  // 다음 단계 (최종 확인을 한 번 거쳤으면 바로 최종 확인으로)
  const next = () => go(reviewed ? 7 : step + 1);

  const loadItems = async (doc: Picked, set: (v: EditableItems | null) => void) => {
    set(null);
    try {
      set(editable(await api<Items>(`/documents/${doc.id}/items`)));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const pickPrice = (d: Picked) => {
    if (priceDoc?.id === d.id) return;
    setPriceDoc(d);
    loadItems(d, setPrice);
    if (!title && d.title) setTitle(`${d.title} 견적서`);
  };
  const pickPurchase = (d: Picked) => {
    if (purchaseDoc?.id === d.id) return;
    setPurchaseDoc(d);
    loadItems(d, setPurchase);
  };
  const pickTemplate = (t: Template | null) => {
    setTemplate(t);
    setTemplateChosen(true);
  };

  // 생성한 견적서를 불러와 고친다 → 최종 확인 단계에서 시작, 생성하면 다음 버전
  const loadGenerated = (g: GeneratedQuote) => {
    const f = g.fields;
    const tpl = templates.data?.find((t) => t.id === f.template_id) ?? null;
    setTemplate(tpl);
    setTemplateChosen(true);
    const att = (k: "price_list" | "purchase") => g.attachments.find((a) => a.kind === k);
    const p = att("price_list");
    const u = att("purchase");
    setPriceDoc(p ? { id: p.document_id, title: p.title } : null);
    setPurchaseDoc(u ? { id: u.document_id, title: u.title } : null);
    setPrice(f.items?.price_list ? editable(f.items.price_list, true) : null);
    setPurchase(f.items?.purchase ? editable(f.items.purchase, true) : null);
    if (f.author) setAuthor((a) => ({ ...a, ...f.author }));
    setTitle(f.title ?? g.title);
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
    template_id: template?.id ?? null,
    price_list_id: priceDoc?.id ?? null,
    price: pickedRows(price),
    purchase_id: purchaseDoc?.id ?? null,
    purchase: pickedRows(purchase),
    author,
    based_on_id: basedOn?.id ?? null,
  });

  const stepOk: Record<number, boolean> = {
    1: templateChosen,
    2: !!priceDoc,
    3: !!price && price.checked.some(Boolean),
    4: !!purchaseDoc,
    5: !!purchase && purchase.checked.some(Boolean),
    6: !!author.name.trim(),
    7: !!title.trim(),
  };
  const stepHint: Record<number, string> = {
    1: "위 '가져오기 > 견적서 양식'에서 양식을 고르세요 (양식이 없으면 기본 양식).",
    2: "위 '가져오기 > 제품 가격표'에서 문서를 하나 고르세요.",
    3: "견적서에 넣을 항목을 체크하고, 값이 다르면 칸을 눌러 고치세요.",
    4: "위 '가져오기 > 매입 금액'에서 문서를 하나 고르세요.",
    5: "견적서에 넣을 매입 항목을 체크하고, 필요하면 고치세요.",
    6: "로그인한 사용자 정보로 채웠습니다. 다르면 고치세요.",
    7: "입력한 내용이 맞는지 확인하고 미리보기를 본 뒤 생성하세요. 고칠 곳이 있으면 위 단계 번호를 누르세요.",
  };

  return (
    <>
      <div className="page-header">
        <h1>견적서 생성</h1>
        <p className="muted">
          가져오기에서 견적서 양식·제품 가격표·매입 금액을 고르고, 아래 순서대로 확인해 견적서를 만듭니다. 만든 견적서는 <Link to="/quotes/created">생성한 견적서</Link>에서 이력과 함께 봅니다.
        </p>
      </div>

      <section className="card">
        <h2 className="section-title">가져오기</h2>
        <div className="filters">
          {IMPORT_TABS.map((t) => (
            <button key={t.key} className={tab === t.key ? "active" : ""} onClick={() => setTab(t.key)}>
              {t.label}
              {(t.key === "template" && templateChosen) || (t.key === "price_list" && priceDoc) || (t.key === "purchase" && purchaseDoc) ? " ✓" : ""}
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
        {tab === "price_list" && <DocPicker docType="price_list" checked={priceDoc?.id ?? null} onPick={pickPrice} />}
        {tab === "purchase" && <DocPicker docType="purchase" checked={purchaseDoc?.id ?? null} onPick={pickPurchase} />}
        {tab === "generated" && <GeneratedPicker checked={basedOn?.id ?? null} onPick={loadGenerated} />}
      </section>

      <section className="card">
        <ol className="stepper">
          {STEPS.map((label, i) => {
            const n = i + 1;
            const reachable = reviewed || n <= step;
            return (
              <li key={n} className={`${n === step ? "current" : ""} ${stepOk[n] ? "done" : ""}`}>
                <button disabled={!reachable} onClick={() => go(n)} title={reviewed ? "이 단계로 돌아가 고치면 바로 최종 확인으로 돌아옵니다" : undefined}>
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
            선택한 양식: <strong>{templateChosen ? (template ? `${template.name} (${template.file_ext === "docx" ? "Word" : "Excel"})` : "기본 양식") : "아직 고르지 않음"}</strong>
          </p>
        )}
        {(step === 2 || step === 4) && (
          <p>
            선택한 문서: <strong>{(step === 2 ? priceDoc : purchaseDoc)?.title ?? ((step === 2 ? priceDoc : purchaseDoc) ? "(제목 없음)" : "아직 고르지 않음")}</strong>
          </p>
        )}
        {step === 3 && <ItemsEditor items={price} onChange={setPrice} empty="제품 가격표를 먼저 고르세요." />}
        {step === 5 && <ItemsEditor items={purchase} onChange={setPurchase} empty="매입 금액 문서를 먼저 고르세요." />}
        {step === 6 && (
          <div className="form-row">
            {AUTHOR_FIELDS.map((f) => (
              <label key={f.key}>
                {f.label}
                {f.key === "name" && <span className="required"> *</span>}
                <input value={author[f.key]} onChange={(e) => setAuthor({ ...author, [f.key]: e.target.value })} />
              </label>
            ))}
          </div>
        )}
        {step === 7 && (
          <FinalStep
            title={title}
            setTitle={setTitle}
            template={templateChosen ? template : undefined}
            priceDoc={priceDoc}
            price={pickedRows(price)}
            purchaseDoc={purchaseDoc}
            purchase={pickedRows(purchase)}
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
        견적서는 고른 양식을 기준으로 만듭니다. 양식(Word·Excel) 안에 <code>{"{{제목}}"}</code> <code>{"{{작성자}}"}</code> <code>{"{{소속}}"}</code>{" "}
        <code>{"{{부서}}"}</code> <code>{"{{이메일}}"}</code> <code>{"{{전화번호}}"}</code> <code>{"{{작성일}}"}</code> 를 적어 두면 그 자리에 값이 들어가고,{" "}
        <code>{"{{제품가격표}}"}</code> <code>{"{{매입금액}}"}</code> 자리에는 체크한 항목 표가 들어갑니다(없으면 문서 끝에 붙음).
      </p>
      <div className="table-wrap">
        <table style={{ minWidth: 760 }}>
          <thead><tr><th style={{ width: 48 }}>선택</th><th>양식 이름</th><th>파일</th><th>올린 사람</th><th>변경 일시</th><th>관리</th></tr></thead>
          <tbody>
            <tr className={selected === 0 ? "highlight" : ""}>
              <td><input type="radio" name="quote-template" checked={selected === 0} onChange={() => onPick(null)} aria-label="기본 양식" /></td>
              <td>기본 양식</td>
              <td className="muted">양식 없이 기본 형식 (PDF·Word·Excel)</td>
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

/** 가져오기 > 제품 가격표 · 매입 금액: 문서 등록에서 올린 문서를 하나 고른다. */
function DocPicker({ docType, checked, onPick }: { docType: "price_list" | "purchase"; checked: number | null; onPick: (d: Picked) => void }) {
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
            <tr key={d.id} className={checked === d.id ? "highlight" : ""}>
              <td><input type="radio" name={`pick-${docType}`} checked={checked === d.id} onChange={() => onPick({ id: d.id, title: d.title })} aria-label={`${d.title ?? "문서"} 선택`} /></td>
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

/** 3·5단계: 뽑은 항목을 체크하고 칸을 고친다. */
function ItemsEditor({ items, onChange, empty }: { items: EditableItems | null; onChange: (v: EditableItems) => void; empty: string }) {
  if (!items) return <p className="muted">{empty}</p>;
  if (!items.rows.length) return <p className="muted">이 문서에서 표 항목을 찾지 못했습니다. 표가 있는 Excel·Word·PDF 를 고르세요.</p>;
  const all = items.checked.every(Boolean);
  const setCell = (r: number, c: number, v: string) =>
    onChange({ ...items, rows: items.rows.map((row, i) => (i === r ? row.map((x, j) => (j === c ? v : x)) : row)) });
  const toggle = (r: number) => onChange({ ...items, checked: items.checked.map((x, i) => (i === r ? !x : x)) });
  return (
    <>
      <p className="muted">{items.checked.filter(Boolean).length} / {items.rows.length}개 체크</p>
      <div className="table-wrap">
        <table className="items-table" style={{ minWidth: Math.max(600, items.columns.length * 140) }}>
          <thead>
            <tr>
              <th style={{ width: 48 }}>
                <input type="checkbox" checked={all} onChange={() => onChange({ ...items, checked: items.rows.map(() => !all) })} aria-label="전체 선택" />
              </th>
              {items.columns.map((c, i) => <th key={i}>{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {items.rows.map((row, r) => (
              <tr key={r} className={items.checked[r] ? "highlight" : ""}>
                <td><input type="checkbox" checked={items.checked[r]} onChange={() => toggle(r)} aria-label={`${r + 1}행 선택`} /></td>
                {row.map((v, c) => (
                  <td key={c}>
                    <input className="cell-input" value={v} onChange={(e) => setCell(r, c, e.target.value)} aria-label={`${r + 1}행 ${items.columns[c]}`} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function SmallTable({ items }: { items: Items }) {
  if (!items.rows.length) return <p className="muted">체크한 항목 없음</p>;
  return (
    <div className="table-wrap">
      <table style={{ minWidth: 500 }}>
        <thead><tr>{items.columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
        <tbody>{items.rows.map((r, i) => <tr key={i}>{r.map((v, j) => <td key={j}>{v}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

/** 7단계: 최종 확인 → 미리보기 → 형식 골라 생성. 미리보기 뒤에 내용을 바꾸면 다시 미리보기를 봐야 생성할 수 있다. */
function FinalStep(props: {
  title: string;
  setTitle: (v: string) => void;
  template: Template | null | undefined;
  priceDoc: Picked | null;
  price: Items;
  purchaseDoc: Picked | null;
  purchase: Items;
  author: Author;
  body: () => object;
  ready: boolean;
  missing: string[];
  basedOn: GeneratedQuote | null;
  created: GeneratedQuote | null;
  onCreated: (g: GeneratedQuote) => void;
  goStep: (n: number) => void;
}) {
  const { template, created } = props;
  const [preview, setPreview] = useState<{ html: string; formats: string[]; key: string } | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [format, setFormat] = useState<string>("");
  const key = JSON.stringify(props.body());
  const previewed = preview?.key === key;
  const runPreview = useMutation({
    mutationFn: () => api<{ html: string; formats: string[] }>("/quote-builder/preview", { method: "POST", json: props.body() }),
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
  const section = (n: number, label: string, children: React.ReactNode) => (
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
      <label style={{ display: "block", marginBottom: 12 }}>
        견적서 제목 <span className="required">*</span>
        <input value={props.title} onChange={(e) => props.setTitle(e.target.value)} placeholder="예: ○○ 고객사 HSM 견적서" />
      </label>
      {section(1, "견적서 양식", <p>{template === undefined ? "아직 고르지 않음" : template ? `${template.name} (${template.file_name})` : "기본 양식"}</p>)}
      {section(2, "제품 가격표", <p>{props.priceDoc?.title ?? (props.priceDoc ? "(제목 없음)" : "아직 고르지 않음")}</p>)}
      {section(3, "가격표 항목", <SmallTable items={props.price} />)}
      {section(4, "매입 금액", <p>{props.purchaseDoc?.title ?? (props.purchaseDoc ? "(제목 없음)" : "아직 고르지 않음")}</p>)}
      {section(5, "매입 항목", <SmallTable items={props.purchase} />)}
      {section(
        6,
        "작성자 정보",
        <p>{AUTHOR_FIELDS.map((f) => `${f.label}: ${props.author[f.key] || "-"}`).join(" · ")}</p>,
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
                {template && f === "pdf" ? " (기본 양식)" : ""}
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
              <h2 style={{ margin: 0 }}>견적서 미리보기{template ? ` · ${template.name}` : " · 기본 양식"}</h2>
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
