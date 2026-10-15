import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .config import settings
from .db import SessionLocal, init_db
from .models import Role, User, UserStatus
from .routers import (
    admin,
    auth,
    community,
    dashboard,
    documents,
    exports,
    guides,
    partner_guides,
    partners,
    sharing,
    vendors,
)
from .security import hash_password


def bootstrap_admin() -> None:
    """설정에 지정된 플랫폼 관리자 계정이 없으면 만든다."""
    if not (settings.admin_email and settings.admin_password):
        return
    email = settings.admin_email.lower()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == email)):
            return
        db.add(
            User(
                email=email,
                password_hash=hash_password(settings.admin_password),
                name="관리자",
                role=Role.PLATFORM_ADMIN,
                status=UserStatus.ACTIVE,
            )
        )
        db.commit()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    bootstrap_admin()
    if settings.embedded_worker:
        # 개발용: 별도 터미널 없이 API 서버 안에서 Worker 를 함께 돌린다.
        from .worker import worker_loop

        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        threading.Thread(target=worker_loop, name="embedded-worker", daemon=True).start()
    yield


app = FastAPI(title="기술 가이드 요약 시스템", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (auth, admin, vendors, partners, documents, guides, exports, partner_guides, community, dashboard, sharing):
    app.include_router(module.router)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "llm_provider": settings.llm_provider}
