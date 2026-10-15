"""초안 일괄 승인: 초안만 승인하고, 실패·생성 중 항목은 남겨 둔다."""

from pathlib import Path

from app.db import SessionLocal
from app.models import SectionSummary, SummaryStatus
from app.worker import run_pending_jobs

from .conftest import ADMIN, login
from .test_flow import _make_vendor_docx, _partner_with_vendor, _signup_and_approve


def test_approve_all_skips_failed(client, tmp_path: Path):
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "일괄파트너", "BulkVendor")
    user = _signup_and_approve(client, admin, "bulk@bulk.example.com", partner["id"])
    src = tmp_path / "v.docx"
    _make_vendor_docx(src)
    with src.open("rb") as f:
        doc_id = client.post("/api/documents", data={"vendor_id": vendor["id"]}, files={"file": ("v.docx", f)}, headers=user).json()["id"]
    run_pending_jobs()
    guide_id = client.post(f"/api/documents/{doc_id}/guides", json={"target_language": "ko"}, headers=user).json()["id"]
    run_pending_jobs()

    # 한 항목을 실패 상태로 만든다.
    items = client.get(f"/api/guides/{guide_id}", headers=user).json()["items"]
    failed_id = next(it["summary"]["id"] for it in items if it["summary"])
    with SessionLocal() as db:
        db.get(SectionSummary, failed_id).status = SummaryStatus.FAILED
        db.commit()

    r = client.post(f"/api/guides/{guide_id}/approve-all", headers=user).json()
    assert r == {"approved": 2, "remaining": 1, "guide_status": "reviewing"}

    # 실패 항목을 재생성해 초안이 되면, 다시 일괄 승인으로 마무리된다.
    client.post(f"/api/guides/{guide_id}/summaries/{failed_id}/regenerate", json={"comment": "다시"}, headers=user)
    run_pending_jobs()
    r = client.post(f"/api/guides/{guide_id}/approve-all", headers=user).json()
    assert r == {"approved": 1, "remaining": 0, "guide_status": "approved"}

    # 다른 파트너사는 일괄 승인할 수 없다.
    other_partner, _ = _partner_with_vendor(client, admin, "일괄다른", "BulkOther")
    other = _signup_and_approve(client, admin, "bulk2@bulk.example.com", other_partner["id"])
    assert client.post(f"/api/guides/{guide_id}/approve-all", headers=other).status_code == 404
