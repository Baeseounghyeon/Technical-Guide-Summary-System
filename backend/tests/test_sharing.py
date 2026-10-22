"""파트너 간 가이드 받기: 목록 → 다운로드 요청 → 관리자 알림·승인(승인 처리는 관리자 기능) → 요청 파트너사 다운로드."""

from pathlib import Path

from app.worker import run_pending_jobs

from .conftest import ADMIN, login
from .test_flow import _make_vendor_docx, _signup_and_approve


def _partner(client, admin, name: str, vendor_ids: list[int]) -> dict:
    p = client.post("/api/admin/partners", json={"name": name}, headers=admin).json()
    client.put(f"/api/admin/partners/{p['id']}/vendors", json={"vendor_ids": vendor_ids}, headers=admin)
    return p


def _exported_guide(client, user, vendor_id: int, tmp_path: Path) -> int:
    src = tmp_path / "owner.docx"
    _make_vendor_docx(src)
    with src.open("rb") as f:
        doc_id = client.post("/api/documents", data={"vendor_id": vendor_id, "title": "오너 설치 가이드"}, files={"file": ("owner.docx", f)}, headers=user).json()["id"]
    run_pending_jobs()
    guide_id = client.post(f"/api/documents/{doc_id}/guides", json={"target_language": "ko"}, headers=user).json()["id"]
    run_pending_jobs()
    client.post(f"/api/guides/{guide_id}/approve-all", headers=user)
    client.post(f"/api/guides/{guide_id}/exports", json={"format": "pptx"}, headers=user)
    run_pending_jobs()
    return guide_id


def test_guide_sharing_with_approval(client, tmp_path):
    admin = login(client, *ADMIN)
    vendor = client.post("/api/admin/vendors", json={"name": "ShareVendor"}, headers=admin).json()
    other_vendor = client.post("/api/admin/vendors", json={"name": "ShareOther"}, headers=admin).json()
    owner_p = _partner(client, admin, "공유소유사", [vendor["id"]])
    req_p = _partner(client, admin, "공유요청사", [vendor["id"]])
    far_p = _partner(client, admin, "공유무관사", [other_vendor["id"]])

    owner_admin = _signup_and_approve(client, admin, "own-admin@share.example.com", owner_p["id"], role="partner_admin")
    uploader = _signup_and_approve(client, admin, "uploader@share.example.com", owner_p["id"])
    owner_eng = _signup_and_approve(client, admin, "own-eng@share.example.com", owner_p["id"])
    requester = _signup_and_approve(client, admin, "req@share.example.com", req_p["id"])
    req_colleague = _signup_and_approve(client, admin, "req2@share.example.com", req_p["id"])
    far = _signup_and_approve(client, admin, "far@share.example.com", far_p["id"])

    guide_id = _exported_guide(client, uploader, vendor["id"], tmp_path)
    export_id = client.get(f"/api/guides/{guide_id}/exports", headers=uploader).json()[0]["id"]
    # 가이드 생성 화면: 요약 가이드가 아직 없는 문서만 (summarized=false)
    titles = lambda q: [d["title"] for d in client.get(f"/api/documents?doc_type=guide&{q}", headers=uploader).json()]  # noqa: E731
    assert titles("summarized=false") == [] and titles("summarized=true") == ["오너 설치 가이드"]

    # 1) 같은 벤더의 다른 파트너사에게만 목록이 보이고, 승인 전에는 받을 수 없다.
    shared = client.get("/api/shared-guides", headers=requester).json()
    assert [(s["title"], s["owner_partner_name"], s["formats"], s["request_status"]) for s in shared] == [
        ("오너 설치 가이드", "공유소유사", ["pptx"], "none")
    ]
    assert client.get("/api/shared-guides", headers=far).json() == []
    assert client.get("/api/shared-guides", headers=uploader).json() == []  # 자기 회사 가이드는 목록에 없음
    assert client.get(f"/api/exports/{export_id}/download", headers=requester).status_code == 404
    assert client.get(f"/api/shared-guides/{guide_id}/exports", headers=requester).status_code == 403
    assert client.post(f"/api/shared-guides/{guide_id}/requests", json={}, headers=far).status_code == 404

    # 2) 요청 → 관리자에게 알림 (승인 처리는 관리자 기능: 소유 회사 관리자·작성자는 승인하지 않는다)
    r = client.post(f"/api/shared-guides/{guide_id}/requests", json={"message": "고객사 설치 지원용"}, headers=requester)
    assert r.status_code == 201, r.text
    req_id = r.json()["id"]
    assert client.post(f"/api/shared-guides/{guide_id}/requests", json={}, headers=req_colleague).status_code == 409

    def request_note(headers):
        items = client.get("/api/notifications", headers=headers).json()["items"]
        return next((n for n in items if n["kind"] == "download_request" and n["related_id"] == req_id), None)

    note = request_note(admin)
    assert note and note["actionable"] and "고객사 설치 지원용" in note["body"] and note["link"] == "/requests/approvals?kind=download"
    for who in (owner_admin, uploader, owner_eng):
        assert request_note(who) is None
        assert client.post(f"/api/download-requests/{req_id}/decision", json={"approve": True}, headers=who).status_code == 404
    assert client.post(f"/api/download-requests/{req_id}/decision", json={"approve": True}, headers=requester).status_code == 404

    # 3) 관리자 승인 → 요청자에게 알림, 요청 파트너사 사용자 모두 다운로드 가능
    r = client.post(f"/api/download-requests/{req_id}/decision", json={"approve": True, "note": "참고용으로만"}, headers=admin)
    assert r.json()["status"] == "approved"
    assert not request_note(admin)["actionable"]  # 처리한 알림은 정리됨
    decision = client.get("/api/notifications", headers=requester).json()["items"][0]
    assert decision["kind"] == "download_decision" and "승인" in decision["title"] and "참고용으로만" in decision["body"]

    exports = client.get(f"/api/shared-guides/{guide_id}/exports", headers=req_colleague).json()
    assert [e["format"] for e in exports] == ["pptx"]
    dl = client.get(f"/api/exports/{export_id}/download", headers=req_colleague)
    assert dl.status_code == 200 and dl.content[:2] == b"PK"
    assert client.get("/api/shared-guides", headers=requester).json()[0]["request_status"] == "approved"
    assert client.get(f"/api/guides/{guide_id}", headers=requester).status_code == 404  # 가이드 편집 화면은 여전히 비공개

    # 4) 알림 읽음 처리
    client.post("/api/notifications/read-all", headers=requester)
    assert client.get("/api/notifications", headers=requester).json()["unread"] == 0

    # 5) 거절 후 다시 요청할 수 있다.
    req_p2 = _partner(client, admin, "공유요청사2", [vendor["id"]])
    requester2 = _signup_and_approve(client, admin, "req3@share.example.com", req_p2["id"])
    rid2 = client.post(f"/api/shared-guides/{guide_id}/requests", json={}, headers=requester2).json()["id"]
    client.post(f"/api/download-requests/{rid2}/decision", json={"approve": False, "note": "내부 문서"}, headers=admin)
    assert client.get(f"/api/exports/{export_id}/download", headers=requester2).status_code == 404
    shared2 = client.get("/api/shared-guides", headers=requester2).json()[0]
    assert shared2["request_status"] == "rejected" and shared2["decision_note"] == "내부 문서"
    assert client.post(f"/api/shared-guides/{guide_id}/requests", json={"message": "재요청"}, headers=requester2).status_code == 201

    incoming = [r for r in client.get("/api/download-requests/incoming", headers=admin).json() if r["guide_id"] == guide_id]
    assert [r["status"] for r in incoming] == ["pending", "rejected", "approved"]
    assert client.get("/api/download-requests/incoming", headers=owner_admin).json() == []
