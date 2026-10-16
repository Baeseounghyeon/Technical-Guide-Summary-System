import { useQuery } from "@tanstack/react-query";
import { api } from "./api";

/** 벤더 이름 → 제품군 → 상세 목록 (서버 catalog.PRODUCT_CATALOG) */
export type Catalog = Record<string, Record<string, string[]>>;

export function useCatalog() {
  return useQuery({ queryKey: ["catalog"], queryFn: () => api<Catalog>("/catalog"), staleTime: Infinity });
}

/** 벤더 옆에 붙는 '제품군'·'상세' 선택칸. 벤더를 고르기 전이나 목록에 없는 벤더면 제품군은 비활성.
 *  상세는 고른 제품군에 상세 항목이 있을 때만 나온다. filter 이면 첫 항목이 '전체', 아니면 '선택 안 함'. */
export default function ProductSelect({
  vendorName, product, detail, onChange, filter = false, width = 200,
}: {
  vendorName: string | null | undefined;
  product: string;
  detail: string;
  onChange: (product: string, detail: string) => void;
  filter?: boolean;
  width?: number;
}) {
  const catalog = useCatalog();
  const families = vendorName ? catalog.data?.[vendorName] : undefined;
  const details = product && families ? families[product] ?? [] : [];
  return (
    <>
      <label style={{ flex: `0 0 ${width}px` }}>
        제품군
        <select value={product} disabled={!families} onChange={(e) => onChange(e.target.value, "")}>
          <option value="">{!vendorName ? "벤더를 먼저 선택" : !families ? "등록된 제품군 없음" : filter ? "전체 제품군" : "선택 안 함"}</option>
          {families && Object.keys(families).map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </label>
      {details.length > 0 && (
        <label style={{ flex: `0 0 ${width}px` }}>
          상세
          <select value={detail} onChange={(e) => onChange(product, e.target.value)}>
            <option value="">{filter ? "전체 상세" : "선택 안 함"}</option>
            {details.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>
      )}
    </>
  );
}

/** 표에 보여 줄 제품 표기: '제품군 · 상세' */
export function productLabel(product: string | null | undefined, detail: string | null | undefined): string {
  return [product, detail].filter(Boolean).join(" · ") || "-";
}
