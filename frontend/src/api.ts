const TOKEN_KEY = "techguide.token";

export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string) {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* 저장소를 쓸 수 없는 환경에서는 새로고침 시 다시 로그인 */
    }
  },
  clear() {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* noop */
    }
  },
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type ApiInit = Omit<RequestInit, "body"> & { json?: unknown; body?: BodyInit };

function authHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(init);
  const token = tokenStore.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return headers;
}

let directUpload: Promise<boolean> | null = null;

/** 서버가 Supabase Storage 직접 업로드를 쓰는지 (서버리스 배포는 요청 크기 제한 4.5MB 때문에 직접 올린다). */
function usesDirectUpload(): Promise<boolean> {
  directUpload ??= fetch("/api/uploads/config")
    .then((r) => r.json())
    .then((d) => Boolean(d.direct_upload))
    .catch(() => false);
  return directUpload;
}

/** 폼의 파일을 저장소에 먼저 올리고, file 대신 storage_key·filename 을 보내도록 바꾼다. */
async function uploadFilesDirectly(form: FormData): Promise<FormData> {
  const out = new FormData();
  for (const [name, value] of form.entries()) {
    if (!(value instanceof File)) {
      out.append(name, value);
      continue;
    }
    const slot = await api<{ key: string; upload_url: string }>("/uploads", { method: "POST", json: { filename: value.name } });
    const put = await fetch(slot.upload_url, {
      method: "PUT",
      headers: { "Content-Type": value.type || "application/octet-stream", "x-upsert": "true" },
      body: value,
    });
    if (!put.ok) throw new ApiError(put.status, "파일 업로드에 실패했습니다. 다시 시도해 주세요.");
    out.append("storage_key", slot.key);
    out.append("filename", value.name);
  }
  return out;
}

/** 서버리스 배포: 작업을 등록한 요청 뒤에 처리를 깨운다 (응답은 기다리지 않음). */
function kickJobs() {
  fetch("/api/jobs/kick", { method: "POST", headers: authHeaders(), keepalive: true }).catch(() => {
    /* 실패해도 1분마다 도는 예약 작업이 이어서 처리한다 */
  });
}

async function request(path: string, init: ApiInit = {}): Promise<Response> {
  const headers = authHeaders(init.headers);
  let body = init.body;
  if (init.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }
  if (body instanceof FormData && (await usesDirectUpload())) {
    body = await uploadFilesDirectly(body);
  }
  const res = await fetch(`/api${path}`, { ...init, headers, body });
  if (res.headers.get("X-Jobs-Queued")) kickJobs();
  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = await res.json();
      message = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    } catch {
      /* 본문이 JSON 이 아닌 경우 */
    }
    if (res.status === 401) tokenStore.clear();
    throw new ApiError(res.status, message);
  }
  return res;
}

export async function api<T>(path: string, init: ApiInit = {}): Promise<T> {
  const res = await request(path, init);
  return (res.status === 204 ? undefined : await res.json()) as T;
}

/** 파일 응답을 받는다. 저장소가 Supabase 면 서버가 짧게 유효한 다운로드 주소를 JSON 으로 주므로 한 번 더 받는다. */
async function fetchFile(path: string): Promise<{ blob: Blob; filename: string | null }> {
  const res = await request(path);
  if (res.headers.get("Content-Type")?.includes("application/json")) {
    const { download_url, filename } = (await res.json()) as { download_url: string; filename?: string };
    const file = await fetch(download_url);
    if (!file.ok) throw new ApiError(file.status, "파일을 받을 수 없습니다.");
    return { blob: await file.blob(), filename: filename ?? null };
  }
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const encoded = /filename\*=utf-8''([^;]+)/i.exec(disposition)?.[1];
  const plain = /filename="?([^";]+)"?/i.exec(disposition)?.[1];
  return { blob: await res.blob(), filename: encoded ? decodeURIComponent(encoded) : (plain ?? null) };
}

/** 인증 헤더가 필요한 파일을 Blob 으로 받는다 (이미지 미리보기 등). */
export async function fetchBlob(path: string): Promise<Blob> {
  return (await fetchFile(path)).blob;
}

/** 인증 헤더가 필요한 파일 다운로드. */
export async function download(path: string): Promise<void> {
  const file = await fetchFile(path);
  const filename = file.filename ?? "download";
  const url = URL.createObjectURL(file.blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
