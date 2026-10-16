import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api";
import { DOC_TYPES } from "../labels";
import { productLabel } from "../ProductSelect";

interface TrashItem {
  id: number;
  title: string | null;
  doc_type: string;
  vendor_name: string;
  product: string | null;
  product_detail: string | null;
  uploaded_by_name: string | null;
  created_at: string;
  deleted_by_name: string | null;
  deleted_at: string;
}

function RestoreIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <path d="M3 4v5h5" />
    </svg>
  );
}

/** 휴지통: 같은 조직에서 삭제한 문서. 복구하면 삭제 전 그대로(등록일·목차·요약 가이드 포함) 원래 자리로 돌아간다. */
export default function TrashPage() {
  const queryClient = useQueryClient();
  const items = useQuery({ queryKey: ["trash"], queryFn: () => api<TrashItem[]>("/trash") });
  const restore = useMutation({
    mutationFn: (id: number) => api(`/trash/${id}/restore`, { method: "POST" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trash"] });
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
  return (
    <>
      <div className="page-header">
        <h1>휴지통</h1>
        <p className="muted">
          같은 조직에서 삭제한 문서입니다. 실수로 지운 문서는 복구하면 삭제 전 상태 그대로 원래 목록의 원래 자리로 돌아갑니다.
        </p>
      </div>
      <section className="card">
        {items.isLoading && <p className="muted">불러오는 중…</p>}
        {items.error && <p className="error">{items.error.message}</p>}
        {restore.error && <p className="error">{restore.error.message}</p>}
        {items.data?.length === 0 && <p className="muted">휴지통이 비어 있습니다.</p>}
        {!!items.data?.length && (
          <div className="table-wrap">
            <table style={{ minWidth: 900 }}>
              <thead>
                <tr>
                  <th>문서 이름</th><th>문서 목적</th><th>벤더</th><th>제품</th><th>등록자</th><th>등록 날짜</th><th>삭제한 사람</th><th>삭제 일시</th><th>복구</th>
                </tr>
              </thead>
              <tbody>
                {items.data.map((d) => (
                  <tr key={d.id}>
                    <td>{d.title ?? `문서 ${d.id}`}</td>
                    <td>{DOC_TYPES.find((t) => t.key === d.doc_type)?.label ?? "-"}</td>
                    <td>{d.vendor_name}</td>
                    <td>{productLabel(d.product, d.product_detail)}</td>
                    <td>{d.uploaded_by_name ?? "-"}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{new Date(d.created_at).toLocaleDateString()}</td>
                    <td>{d.deleted_by_name ?? "-"}</td>
                    <td style={{ whiteSpace: "nowrap" }}>{new Date(d.deleted_at).toLocaleString()}</td>
                    <td>
                      <button
                        className="icon-button sm"
                        title="복구"
                        aria-label={`${d.title ?? "문서"} 복구`}
                        disabled={restore.isPending}
                        onClick={() => restore.mutate(d.id)}
                      >
                        <RestoreIcon />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
