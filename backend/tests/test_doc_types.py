"""문서 종류(규격서·기술 가이드·브로슈어): 등록할 때 고르고, 종류·벤더별로 목록을 본다."""

from pathlib import Path

from app.worker import run_pending_jobs

from .conftest import ADMIN, login
from .test_flow import _make_vendor_docx, _partner_with_vendor, _signup_and_approve


def test_documents_by_type_and_vendor(client, tmp_path: Path):
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "종류파트너", "TypeVendorA")
    _, vendor_b = _partner_with_vendor(client, admin, "종류파트너B", "TypeVendorB")
    client.put(f"/api/admin/partners/{partner['id']}/vendors", json={"vendor_ids": [vendor["id"], vendor_b["id"]]}, headers=admin)
    user = _signup_and_approve(client, admin, "types@t.example.com", partner["id"])
    src = tmp_path / "v.docx"
    _make_vendor_docx(src)

    def upload(vendor_id: int, doc_type: str | None, title: str) -> dict:
        data = {"vendor_id": vendor_id, "title": title, "description": f"{title} 설명"}
        if doc_type:
            data["doc_type"] = doc_type
        with src.open("rb") as f:
            r = client.post("/api/documents", data=data, files={"file": ("v.docx", f)}, headers=user)
        assert r.status_code == 201, r.text
        return r.json()

    spec = upload(vendor["id"], "spec", "A 규격서")
    assert spec["doc_type"] == "spec" and spec["description"] == "A 규격서 설명" and spec["uploaded_by_name"]
    upload(vendor["id"], None, "A 가이드")  # 종류를 안 고르면 기술 가이드
    upload(vendor_b["id"], "brochure", "B 브로슈어")
    run_pending_jobs()  # 다른 테스트에 대기 작업을 남기지 않는다

    def titles(query: str) -> list[str]:
        return sorted(d["title"] for d in client.get(f"/api/documents?{query}", headers=user).json())

    assert titles("doc_type=spec") == ["A 규격서"]
    assert titles("doc_type=guide") == ["A 가이드"]
    assert titles(f"doc_type=brochure&vendor_id={vendor['id']}") == []
    assert titles(f"doc_type=brochure&vendor_id={vendor_b['id']}") == ["B 브로슈어"]
    assert client.post(
        "/api/documents", data={"vendor_id": vendor["id"], "doc_type": "unknown", "url": "https://example.com"}, headers=user
    ).status_code == 422
