"""대시보드: 본인이 올린 문서만, 진행 단계별로 집계한다."""

from pathlib import Path

from app.worker import run_pending_jobs

from .conftest import ADMIN, login
from .test_flow import _make_vendor_docx, _partner_with_vendor, _signup_and_approve


def _upload(client, user, vendor_id: int, path: Path, name: str) -> int:
    with path.open("rb") as f:
        return client.post("/api/documents", data={"vendor_id": vendor_id}, files={"file": (name, f)}, headers=user).json()["id"]


def test_dashboard_counts(client, tmp_path):
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "대시보드파트너", "DashVendor")
    user = _signup_and_approve(client, admin, "dash@dash.example.com", partner["id"])
    colleague = _signup_and_approve(client, admin, "dash2@dash.example.com", partner["id"])

    assert client.get("/api/dashboard", headers=user).json()["counts"]["total"] == 0

    src = tmp_path / "v.docx"
    _make_vendor_docx(src)
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf")

    done_doc = _upload(client, user, vendor["id"], src, "done.docx")
    review_doc = _upload(client, user, vendor["id"], src, "review.docx")
    idle_doc = _upload(client, user, vendor["id"], src, "idle.docx")
    _upload(client, user, vendor["id"], broken, "broken.pdf")
    _upload(client, colleague, vendor["id"], src, "colleague.docx")  # 다른 사람 문서는 세지 않는다
    run_pending_jobs()

    done_guide = client.post(f"/api/documents/{done_doc}/guides", json={"target_language": "ko"}, headers=user).json()["id"]
    client.post(f"/api/documents/{review_doc}/guides", json={"target_language": "ko"}, headers=user)
    run_pending_jobs()
    client.post(f"/api/guides/{done_guide}/approve-all", headers=user)
    client.post(f"/api/guides/{done_guide}/exports", json={"format": "docx"}, headers=user)
    run_pending_jobs()

    data = client.get("/api/dashboard", headers=user).json()
    assert data["counts"] == {"total": 4, "completed": 1, "in_progress": 2, "failed": 1, "exports": 1, "pending_reviews": 3}
    stages = {d["id"]: d["stage"] for d in data["documents"]}
    assert stages[done_doc] == "exported" and stages[review_doc] == "reviewing" and stages[idle_doc] == "not_started"
    row = next(d for d in data["documents"] if d["id"] == done_doc)
    assert row["vendor_name"] == "DashVendor" and row["approved_sections"] == row["total_sections"] == 3

    assert client.get("/api/dashboard", headers=colleague).json()["counts"]["total"] == 1
