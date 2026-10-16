"""Vercel Python 함수 진입점: backend/app 의 FastAPI 앱을 그대로 노출한다.

vercel.json 이 /api/* 요청을 모두 이 함수(/api/index?__path=...)로 보낸다.
Vercel 이 함수에 넘기는 경로가 원래 주소일 수도, 재작성된 /api/index 일 수도 있으므로
__path 가 있으면 원래 경로(/api/...)로 되돌린 뒤 FastAPI 에 넘긴다.
"""

import sys
from pathlib import Path
from urllib.parse import parse_qsl, quote, unquote, urlencode

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app as fastapi_app  # noqa: E402


async def app(scope, receive, send):
    if scope["type"] == "http":
        query = parse_qsl(scope.get("query_string", b"").decode(), keep_blank_values=True)
        rest = [(k, v) for k, v in query if k != "__path"]
        original = next((v for k, v in query if k == "__path"), None)
        if original is not None:
            path = "/api/" + unquote(original).lstrip("/")
            scope = {
                **scope,
                "path": path,
                "raw_path": quote(path).encode(),
                "query_string": urlencode(rest).encode(),
            }
    await fastapi_app(scope, receive, send)
