"""견적서 문서, 사용자 단위 가이드 공유(조직 → 사용자), 30일 미접속 정지와 관리자 정지 해제."""

from datetime import timedelta
from pathlib import Path

from app.db import SessionLocal
from app.models import User, utcnow
from app.worker import run_pending_jobs

from .conftest import ADMIN, login
from .test_flow import _make_vendor_docx, _partner_with_vendor, _signup_and_approve


def _me(client, headers) -> dict:
    return client.get("/api/auth/me", headers=headers).json()


def test_quote_document_type(client, tmp_path: Path):
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "견적파트너", "QuoteDocVendor")
    sales = _signup_and_approve(client, admin, "quote-sales@q.example.com", partner["id"])
    client.post(f"/api/admin/users/{_me(client, sales)['id']}/approve", json={"partner_id": partner["id"], "track": "sales"}, headers=admin)
    engineer = _signup_and_approve(client, admin, "quote-eng@q.example.com", partner["id"])
    src = tmp_path / "q.docx"
    _make_vendor_docx(src)
    data = {"vendor_id": vendor["id"], "doc_type": "quote", "title": "견적서 A"}
    with src.open("rb") as f:
        r = client.post("/api/documents", data=data, files={"file": ("q.docx", f)}, headers=sales)
    assert r.status_code == 201, r.text
    with src.open("rb") as f:  # 엔지니어는 견적서를 올릴 수 없고, 같은 조직 것은 볼 수 있다
        assert client.post("/api/documents", data=data, files={"file": ("q.docx", f)}, headers=engineer).status_code == 403
    run_pending_jobs()
    rows = client.get(f"/api/documents?doc_type=quote&partner_id={partner['id']}", headers=engineer).json()
    assert [d["title"] for d in rows] == ["견적서 A"]


def test_user_shares(client, tmp_path: Path):
    admin = login(client, *ADMIN)
    partner_a, vendor = _partner_with_vendor(client, admin, "공유A조직", "UserShareVendor")
    partner_b, _ = _partner_with_vendor(client, admin, "공유B조직", "UserShareVendorB")
    owner = _signup_and_approve(client, admin, "owner@us.example.com", partner_a["id"])
    b1 = _signup_and_approve(client, admin, "b1@us.example.com", partner_b["id"])
    b2 = _signup_and_approve(client, admin, "b2@us.example.com", partner_b["id"])
    src = tmp_path / "g.docx"
    _make_vendor_docx(src)
    with src.open("rb") as f:
        doc = client.post(
            "/api/documents", data={"vendor_id": vendor["id"], "title": "공유 가이드"}, files={"file": ("g.docx", f)}, headers=owner
        ).json()
    run_pending_jobs()
    b1_id, b2_id = _me(client, b1)["id"], _me(client, b2)["id"]

    users = client.get(f"/api/organizations/{partner_b['id']}/users", headers=owner).json()
    assert {u["id"] for u in users} == {b1_id, b2_id}
    # 조직과 사용자가 맞지 않으면 거절
    bad = {"document_id": doc["id"], "partner_id": partner_a["id"], "user_ids": [b1_id]}
    assert client.post("/api/user-shares", json=bad, headers=owner).status_code == 400
    assert client.post("/api/user-shares", json={**bad, "user_ids": []}, headers=owner).status_code == 400
    # 다른 사람은 공유할 수 없다
    ok = {"document_id": doc["id"], "partner_id": partner_b["id"], "user_ids": [b1_id]}
    assert client.post("/api/user-shares", json=ok, headers=b2).status_code == 404
    r = client.post("/api/user-shares", json=ok, headers=owner)
    assert r.status_code == 201, r.text
    assert client.post("/api/user-shares", json=ok, headers=owner).status_code == 409

    # 고른 사용자만 볼 수 있다 (같은 조직의 다른 사용자는 못 봄)
    assert [d["title"] for d in client.get("/api/documents?shared_to_me=true", headers=b1).json()] == ["공유 가이드"]
    assert client.get("/api/documents?shared_to_me=true", headers=b2).json() == []
    assert client.get(f"/api/documents/{doc['id']}", headers=b2).status_code == 404
    assert client.get(f"/api/documents/{doc['id']}", headers=b1).json()["access"] == "shared"

    shares = client.get("/api/user-shares", headers=owner).json()
    assert [(s["partner_name"], s["user_id"]) for s in shares] == [("공유B조직", b1_id)]
    assert client.delete(f"/api/user-shares/{shares[0]['id']}", headers=b2).status_code == 404
    assert client.delete(f"/api/user-shares/{shares[0]['id']}", headers=owner).status_code == 204
    assert client.get(f"/api/documents/{doc['id']}", headers=b1).status_code == 404


def test_inactive_users_are_suspended(client):
    admin = login(client, *ADMIN)
    partner, _ = _partner_with_vendor(client, admin, "미접속조직", "InactiveVendor")
    user = _signup_and_approve(client, admin, "idle@i.example.com", partner["id"])
    user_id = _me(client, user)["id"]

    def set_last_seen(days_ago: int, email: str = "idle@i.example.com") -> None:
        with SessionLocal() as db:
            u = db.query(User).filter(User.email == email).one()
            u.last_seen_at = utcnow() - timedelta(days=days_ago)
            db.commit()

    set_last_seen(29)
    assert client.get("/api/auth/me", headers=user).status_code == 200
    set_last_seen(31)
    r = client.get("/api/auth/me", headers=user)
    assert r.status_code == 403 and "30일" in r.json()["detail"]
    r = client.post("/api/auth/login", json={"email": "idle@i.example.com", "password": "engineer-pass-1"})
    assert r.status_code == 403 and "30일" in r.json()["detail"]
    row = next(u for u in client.get("/api/admin/users", headers=admin).json() if u["id"] == user_id)
    assert row["status"] == "suspended" and row["suspended_reason"] == "inactive"

    # 관리자가 정지 해제하면 다시 쓸 수 있다
    assert client.post(f"/api/admin/users/{user_id}/reactivate", headers=admin).status_code == 200
    assert client.post("/api/auth/login", json={"email": "idle@i.example.com", "password": "engineer-pass-1"}).status_code == 200
    assert client.post(f"/api/admin/users/{user_id}/reactivate", headers=admin).status_code == 409

    # 관리자는 오래 접속하지 않아도 정지되지 않는다
    set_last_seen(90, ADMIN[0])
    assert client.get("/api/auth/me", headers=admin).status_code == 200
