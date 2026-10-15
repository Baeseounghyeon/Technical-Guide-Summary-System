"""관리자 가입자 목록: 소속, 할당된 도메인, 읽기 전용 열람 권한, 권한·상태."""

from .conftest import ADMIN, login
from .test_flow import _partner_with_vendor, _signup_and_approve


def test_admin_user_list(client):
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "가입자파트너", "MemberVendorA")
    _, other_vendor = _partner_with_vendor(client, admin, "가입자다른", "MemberVendorB")
    user = _signup_and_approve(client, admin, "member@member.example.com", partner["id"], role="partner_admin")
    client.post(
        "/api/auth/signup",
        json={"email": "waiting@member.example.com", "password": "waiting-pass-1", "name": "대기자",
              "company_name": "신규회사", "phone": "010-1111-2222"},
    )

    # 다른 도메인 읽기 전용 열람 승인
    gid = client.post(f"/api/community/{other_vendor['id']}/access-requests", json={"reason": "r", "days": 5}, headers=user).json()["id"]
    client.post(f"/api/admin/access-requests/{gid}/decision", json={"approve": True}, headers=admin)

    users = {u["email"]: u for u in client.get("/api/admin/users", headers=admin).json()}
    member = users["member@member.example.com"]
    assert member["partner_name"] == "가입자파트너" and member["role"] == "partner_admin"
    assert member["domains"] == ["MemberVendorA"]
    assert [g["vendor_name"] for g in member["read_grants"]] == ["MemberVendorB"]

    waiting = users["waiting@member.example.com"]
    assert waiting["status"] == "pending" and waiting["phone"] == "010-1111-2222"
    assert waiting["domains"] == [] and waiting["company_name"] == "신규회사"

    assert "MemberVendorA" in users["admin@example.com"]["domains"]  # 플랫폼 관리자는 전체
    pending = client.get("/api/admin/users", params={"status": "pending"}, headers=admin).json()
    assert "member@member.example.com" not in {u["email"] for u in pending}

    # 관리자가 아니면 볼 수 없다.
    assert client.get("/api/admin/users", headers=user).status_code == 403
