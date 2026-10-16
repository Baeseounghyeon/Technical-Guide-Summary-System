"""Vercel Python 함수 진입점: backend/app 의 FastAPI 앱을 그대로 노출한다.

vercel.json 이 /api/* 요청을 모두 이 함수로 보낸다.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.main import app  # noqa: E402,F401
