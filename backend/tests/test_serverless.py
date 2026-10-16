"""서버리스(Vercel) 작업 처리: 시간 제한으로 멈춘 요약을 다음 호출에서 이어서 끝낸다."""

from pathlib import Path

from app import worker
from app.config import settings
from app.services import jobs

from .conftest import ADMIN, login
from .test_flow import _make_vendor_docx, _partner_with_vendor, _signup_and_approve


def test_summary_resumes_across_time_limited_runs(client, tmp_path: Path, monkeypatch):
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "서버리스파트너", "ServerlessVendor")
    user = _signup_and_approve(client, admin, "serverless@sl.example.com", partner["id"])
    monkeypatch.setattr(settings, "job_time_budget_seconds", 240)
    monkeypatch.setattr(settings, "cron_secret", None)

    # 처리 한 번에 시간 확인 3회까지만 '남은 시간 있음'으로 답한다 (= 요약 2건 후 멈춤).
    budget = {"n": 0}
    monkeypatch.setattr(worker, "set_deadline", lambda seconds: budget.update(n=3))

    def fake_time_left() -> float:
        budget["n"] -= 1
        return 1000 if budget["n"] >= 0 else 0

    monkeypatch.setattr(jobs, "time_left", fake_time_left)

    src = tmp_path / "v.docx"
    _make_vendor_docx(src)
    with src.open("rb") as f:
        r = client.post("/api/documents", data={"vendor_id": vendor["id"]}, files={"file": ("v.docx", f)}, headers=user)
    assert r.headers.get("x-jobs-queued") == "1"
    doc_id = r.json()["id"]
    assert client.post("/api/jobs/kick", headers=user).json() == {"processed": 1, "remaining": False}

    r = client.post(f"/api/documents/{doc_id}/guides", json={"target_language": "ko"}, headers=user)
    assert r.headers.get("x-jobs-queued") == "1"
    guide_id = r.json()["id"]

    # 1회차: 3개 중 2개만 요약하고 멈춘다.
    assert client.post("/api/jobs/kick", headers=user).json() == {"processed": 1, "remaining": True}
    guide = client.get(f"/api/guides/{guide_id}", headers=user).json()
    statuses = sorted(it["summary"]["status"] for it in guide["items"] if it["summary"])
    assert statuses == ["draft", "draft", "pending"]
    assert guide["status"] == "summarizing"

    # 2회차: 남은 1개와 개요를 마치고 검토 단계로 넘어간다.
    assert client.post("/api/jobs/kick", headers=user).json() == {"processed": 1, "remaining": False}
    guide = client.get(f"/api/guides/{guide_id}", headers=user).json()
    assert {it["summary"]["status"] for it in guide["items"] if it["summary"]} == {"draft"}
    assert guide["status"] == "reviewing"
    assert guide["overview"]


def test_cron_endpoint_requires_secret(client, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "test-cron-secret")
    assert client.get("/api/jobs/run").status_code == 401
    assert client.get("/api/jobs/run", headers={"Authorization": "Bearer wrong"}).status_code == 401
    r = client.get("/api/jobs/run", headers={"Authorization": "Bearer test-cron-secret"})
    assert r.status_code == 200
    monkeypatch.setattr(settings, "cron_secret", None)
    assert client.get("/api/jobs/run", headers={"Authorization": "Bearer None"}).status_code == 401
