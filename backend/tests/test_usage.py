"""AI 사용 한도: 회사별 월 처리량, 같은 문서 중복 요약 방지, 하루 재생성 횟수, 전체 월 예산, 비용 기록."""

from pathlib import Path

from app.config import settings
from app.db import SessionLocal
from app.models import UsageRecord
from app.services.llm.base import LLMUsage
from app.services.usage import add_tokens, cost_of
from app.worker import run_pending_jobs

from .conftest import ADMIN, login
from .test_flow import _make_vendor_docx, _partner_with_vendor, _signup_and_approve


def _upload(client, user, vendor_id: int, tmp_path: Path) -> int:
    src = tmp_path / "v.docx"
    _make_vendor_docx(src)
    with src.open("rb") as f:
        doc_id = client.post("/api/documents", data={"vendor_id": vendor_id}, files={"file": ("v.docx", f)}, headers=user).json()["id"]
    run_pending_jobs()
    return doc_id


def test_partner_quota_and_duplicate_guard(client, tmp_path):
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "한도파트너", "QuotaVendor")
    user = _signup_and_approve(client, admin, "quota@q.example.com", partner["id"])
    doc_id = _upload(client, user, vendor["id"], tmp_path)
    assert client.put(f"/api/admin/partners/{partner['id']}/quota", json={"monthly_page_quota": 2}, headers=admin).status_code == 200

    usage = client.get(f"/api/usage?document_id={doc_id}", headers=user).json()
    assert usage["estimate_pages"] == 1 and usage["remaining_pages"] == 2 and not usage["unlimited"]

    assert client.post(f"/api/documents/{doc_id}/guides", json={"target_language": "ko"}, headers=user).status_code == 201
    # 같은 문서·같은 언어를 다시 요약하면 비용만 두 번 든다 → 막는다
    r = client.post(f"/api/documents/{doc_id}/guides", json={"target_language": "ko"}, headers=user)
    assert r.status_code == 409
    assert client.post(f"/api/documents/{doc_id}/guides", json={"target_language": "en"}, headers=user).status_code == 201
    # 한도(2쪽)를 다 썼으므로 다음 요약은 거절
    r = client.post(f"/api/documents/{doc_id}/guides", json={"target_language": "ja"}, headers=user)
    assert r.status_code == 403 and "한도" in r.json()["detail"]
    run_pending_jobs()

    overview = client.get("/api/admin/usage", headers=admin).json()
    row = next(p for p in overview["partners"] if p["id"] == partner["id"])
    assert row["used_pages"] == 2 and row["quota_pages"] == 2 and row["custom_quota"]
    # 플랫폼 관리자는 회사 한도와 무관하다
    assert client.get("/api/usage", headers=admin).json()["unlimited"]


def test_daily_regenerate_limit_and_budget(client, tmp_path, monkeypatch):
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "재생성파트너", "RegenVendor")
    user = _signup_and_approve(client, admin, "regen@r.example.com", partner["id"])
    doc_id = _upload(client, user, vendor["id"], tmp_path)
    guide_id = client.post(f"/api/documents/{doc_id}/guides", json={"target_language": "ko"}, headers=user).json()["id"]
    run_pending_jobs()
    sid = next(it["summary"]["id"] for it in client.get(f"/api/guides/{guide_id}", headers=user).json()["items"] if it["summary"])

    monkeypatch.setattr(settings, "daily_regenerate_limit", 1)
    base = f"/api/guides/{guide_id}/summaries/{sid}/regenerate"
    assert client.post(base, json={"comment": "짧게"}, headers=user).status_code == 200
    run_pending_jobs()
    r = client.post(base, json={"comment": "더 짧게"}, headers=user)
    assert r.status_code == 429 and "하루" in r.json()["detail"]

    # 전체 월 예산을 넘으면 관리자 요청도 막는다
    with SessionLocal() as db:
        db.add(UsageRecord(kind="summarize", pages=0, cost_usd=5.0))
        db.commit()
    monkeypatch.setattr(settings, "monthly_budget_usd", 1.0)
    r = client.post(f"/api/documents/{doc_id}/guides", json={"target_language": "en"}, headers=admin)
    assert r.status_code == 503 and "예산" in r.json()["detail"]


def test_token_cost_is_recorded():
    usages = [LLMUsage("claude-opus-5-5", input_tokens=1_000_000, output_tokens=100_000)]
    assert round(cost_of(usages), 4) == 6.0  # 입력 $4 + 출력 $2
    with SessionLocal() as db:
        record = UsageRecord(kind="summarize", pages=3)
        db.add(record)
        db.flush()
        add_tokens(db, record.id, usages)
        add_tokens(db, record.id, [LLMUsage("claude-sonnet-5-5", input_tokens=0, output_tokens=1_000_000)])
        assert record.output_tokens == 1_100_000 and round(record.cost_usd, 4) == 16.0
        db.rollback()
