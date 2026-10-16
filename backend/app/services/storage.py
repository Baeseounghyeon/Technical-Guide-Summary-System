"""업로드·생성 파일 저장소: PC 폴더(local) 또는 Supabase Storage(supabase).

DB 의 file_path 류 컬럼에는 save() 가 돌려준 참조 문자열을 저장한다.
- local: 파일의 절대 경로 (기존 데이터와 같은 형식)
- supabase: 버킷 안의 객체 키 (예: "uploads/1a2b.pdf")

서버리스(Vercel)는 디스크가 요청마다 사라지므로 supabase 를 쓴다.
"""

import mimetypes
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO
from urllib.parse import quote

import httpx
from fastapi import HTTPException, status
from fastapi.responses import FileResponse, JSONResponse, Response

from ..config import settings


def _guess_type(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


class LocalStorage:
    direct_upload = False

    def save(self, key: str, data: bytes | BinaryIO) -> str:
        path = settings.storage_dir / key
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            with path.open("wb") as f:
                shutil.copyfileobj(data, f)
        return str(path)

    @contextmanager
    def local_path(self, ref: str) -> Iterator[Path]:
        yield Path(ref)

    def exists(self, ref: str) -> bool:
        return Path(ref).is_file()

    def response(self, ref: str, filename: str, media_type: str) -> Response:
        return FileResponse(ref, media_type=media_type, filename=filename)

    def inline_response(self, ref: str, media_type: str) -> Response:
        return FileResponse(ref, media_type=media_type)

    def sign_upload(self, key: str) -> str:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "이 서버는 직접 업로드를 쓰지 않습니다.")


class SupabaseStorage:
    """Supabase Storage REST API. 비공개 버킷에 서버 전용 키(service role / secret)로 접근한다."""

    direct_upload = True

    def __init__(self) -> None:
        if not (settings.supabase_url and settings.supabase_service_key):
            raise RuntimeError("STORAGE_BACKEND=supabase 에는 SUPABASE_URL 과 SUPABASE_SERVICE_KEY 가 필요합니다.")
        self.base = settings.supabase_url.rstrip("/") + "/storage/v1"
        self.bucket = settings.supabase_bucket
        key = settings.supabase_service_key
        headers = {"apikey": key}
        # 예전 형식(JWT) service_role 키는 Authorization 에도 넣어야 한다. 새 sb_secret_ 키는 apikey 만으로 된다.
        if not key.startswith("sb_"):
            headers["Authorization"] = f"Bearer {key}"
        self.client = httpx.Client(base_url=self.base, headers=headers, timeout=120)
        self._bucket_ready = False

    def _object(self, key: str) -> str:
        return f"/object/{self.bucket}/{quote(key)}"

    def _ensure_bucket(self) -> None:
        if self._bucket_ready:
            return
        r = self.client.get(f"/bucket/{self.bucket}")
        if r.status_code != 200:
            r = self.client.post("/bucket", json={"id": self.bucket, "name": self.bucket, "public": False})
            if r.status_code not in (200, 201) and "already exists" not in r.text.lower():
                raise RuntimeError(f"Supabase 버킷 생성 실패: {r.status_code} {r.text[:300]}")
        self._bucket_ready = True

    def save(self, key: str, data: bytes | BinaryIO) -> str:
        self._ensure_bucket()
        body = data if isinstance(data, bytes) else data.read()
        r = self.client.post(
            self._object(key), content=body, headers={"Content-Type": _guess_type(key), "x-upsert": "true"}
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Supabase 업로드 실패: {r.status_code} {r.text[:300]}")
        return key

    @contextmanager
    def local_path(self, ref: str) -> Iterator[Path]:
        """파서·문서 생성기가 경로를 요구하므로 임시 파일로 받아 넘긴다."""
        r = self.client.get(self._object(ref))
        if r.status_code != 200:
            raise RuntimeError(f"Supabase 파일을 받을 수 없습니다 ({ref}): {r.status_code}")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / Path(ref).name
            path.write_bytes(r.content)
            yield path

    def exists(self, ref: str) -> bool:
        return self.client.head(self._object(ref)).status_code == 200

    def _signed_url(self, ref: str, download: str | None = None) -> str:
        r = self.client.post(f"/object/sign/{self.bucket}/{quote(ref)}", json={"expiresIn": 300})
        if r.status_code != 200:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "파일을 찾을 수 없습니다.")
        url = self.base + r.json()["signedURL"]
        if download is not None:
            url += f"&download={quote(download)}"
        return url

    def response(self, ref: str, filename: str, media_type: str) -> Response:
        # Vercel 함수는 응답 크기 제한(4.5MB)이 있으므로 파일 대신 짧게 유효한 다운로드 주소를 준다.
        return JSONResponse({"download_url": self._signed_url(ref, filename), "filename": filename})

    def inline_response(self, ref: str, media_type: str) -> Response:
        return JSONResponse({"download_url": self._signed_url(ref)})

    def sign_upload(self, key: str) -> str:
        """브라우저가 서버를 거치지 않고 바로 올릴 수 있는 1회용 업로드 주소."""
        self._ensure_bucket()
        r = self.client.post(f"/object/upload/sign/{self.bucket}/{quote(key)}")
        if r.status_code != 200:
            raise RuntimeError(f"Supabase 업로드 주소 발급 실패: {r.status_code} {r.text[:300]}")
        return self.base + r.json()["url"]


_storage: LocalStorage | SupabaseStorage | None = None


def get_storage() -> LocalStorage | SupabaseStorage:
    global _storage
    if _storage is None:
        _storage = SupabaseStorage() if settings.storage_backend == "supabase" else LocalStorage()
    return _storage
