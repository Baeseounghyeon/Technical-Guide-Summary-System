import os
import tempfile
from pathlib import Path

# app 을 가져오기 전에 테스트 전용 DB·저장소를 지정한다.
_tmp = Path(tempfile.mkdtemp(prefix="techguide-test-"))
os.environ.update(
    {
        "DATABASE_URL": f"sqlite:///{(_tmp / 'test.db').as_posix()}",
        "STORAGE_DIR": str(_tmp / "storage"),
        "LLM_PROVIDER": "mock",
        "EMBEDDED_WORKER": "false",  # 테스트는 run_pending_jobs() 로 직접 처리
        "ADMIN_EMAIL": "admin@example.com",
        "ADMIN_PASSWORD": "admin-test-password",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

ADMIN = ("admin@example.com", "admin-test-password")


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def login(client: TestClient, email: str, password: str) -> dict:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}
