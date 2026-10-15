"""3단계: 벤더 도메인 커뮤니티 — 같은 도메인 파트너 간 공유, 타 도메인 차단, 관리자 승인 시 기간 한정 읽기 전용."""

from datetime import datetime, timedelta, timezone

from app.db import SessionLocal
from app.models import AccessGrant

from .conftest import ADMIN, login
from .test_flow import _signup_and_approve


def _setup(client):
    admin = login(client, *ADMIN)
    vendor_a = client.post("/api/admin/vendors", json={"name": "CommVendorA"}, headers=admin).json()
    vendor_b = client.post("/api/admin/vendors", json={"name": "CommVendorB"}, headers=admin).json()
    partners = {}
    for name, vendor in (("커뮤A1", vendor_a), ("커뮤A2", vendor_a), ("커뮤B1", vendor_b)):
        p = client.post("/api/admin/partners", json={"name": name}, headers=admin).json()
        client.put(f"/api/admin/partners/{p['id']}/vendors", json={"vendor_ids": [vendor["id"]]}, headers=admin)
        partners[name] = p
    a1 = _signup_and_approve(client, admin, "a1@comm.example.com", partners["커뮤A1"]["id"])
    a2 = _signup_and_approve(client, admin, "a2@comm.example.com", partners["커뮤A2"]["id"])
    b1 = _signup_and_approve(client, admin, "b1@comm.example.com", partners["커뮤B1"]["id"])
    return admin, vendor_a, vendor_b, a1, a2, b1


def _partner_id(client, admin, name: str) -> int:
    return next(p["id"] for p in client.get("/api/admin/partners", headers=admin).json() if p["name"] == name)


def test_domain_community_and_access_grants(client):
    admin, vendor_a, vendor_b, a1, a2, b1 = _setup(client)
    va = vendor_a["id"]

    # 1) 같은 도메인의 다른 파트너사끼리 이슈 공유
    r = client.post(
        f"/api/community/{va}/posts",
        json={"title": "업그레이드 후 VPN 끊김", "body": "4.3 업그레이드 후 IPsec 터널이 재협상되지 않음",
              "product": "AER-500", "version": "4.3", "tags": ["#vpn", "upgrade", "vpn"]},
        headers=a1,
    )
    assert r.status_code == 201, r.text
    post = r.json()
    assert post["tags"] == ["vpn", "upgrade"] and post["author"]["partner_name"] == "커뮤A1"

    r = client.post(f"/api/community/posts/{post['id']}/comments", json={"body": "DPD 타이머를 30초로 바꾸면 해결됩니다."}, headers=a2)
    assert r.status_code == 201
    comment_id = r.json()["comments"][0]["id"]
    assert r.json()["comments"][0]["author"]["partner_name"] == "커뮤A2"

    # 해결 표시는 작성자만, 해결 댓글 지정
    assert client.patch(f"/api/community/posts/{post['id']}/status", json={"status": "resolved"}, headers=a2).status_code == 403
    r = client.patch(f"/api/community/posts/{post['id']}/status", json={"status": "resolved", "solution_comment_id": comment_id}, headers=a1)
    assert r.json()["status"] == "resolved" and r.json()["solution_comment_id"] == comment_id

    # 검색·필터
    assert len(client.get(f"/api/community/{va}/posts", params={"q": "IPsec"}, headers=a2).json()) == 1
    assert len(client.get(f"/api/community/{va}/posts", params={"tag": "vpn", "status": "resolved"}, headers=a2).json()) == 1
    assert client.get(f"/api/community/{va}/posts", params={"q": "없는말"}, headers=a2).json() == []

    # 온라인 세션 일정 + 참석
    starts = datetime.now(timezone(timedelta(hours=9))) + timedelta(days=3)
    r = client.post(
        f"/api/community/{va}/events",
        json={"title": "4.3 업그레이드 공유 세션", "starts_at": starts.isoformat(), "ends_at": (starts + timedelta(hours=1)).isoformat(),
              "join_url": "https://meet.example.com/abc"},
        headers=a1,
    )
    assert r.status_code == 201, r.text
    event = r.json()
    # +09:00 으로 보낸 시각이 UTC 로 정확히 저장된다.
    assert datetime.fromisoformat(event["starts_at"]) == starts
    assert client.post(f"/api/community/events/{event['id']}/rsvp", headers=a2).json()["attendee_count"] == 1
    assert len(client.get(f"/api/community/{va}/events", headers=a2).json()) == 1
    assert client.get(f"/api/community/{va}/events", params={"scope": "past"}, headers=a2).json() == []

    # 2) 다른 벤더 도메인 파트너는 기본 차단
    domains = {d["vendor_name"]: d for d in client.get("/api/community/domains", headers=b1).json()}
    assert domains["CommVendorA"]["access"] == "none" and domains["CommVendorB"]["access"] == "member"
    assert domains["CommVendorA"]["post_count"] == 0  # 접근 못 하는 도메인 정보는 노출하지 않음
    assert client.get(f"/api/community/{va}/posts", headers=b1).status_code == 403
    assert client.get(f"/api/community/posts/{post['id']}", headers=b1).status_code == 404
    assert client.post(f"/api/community/{va}/posts", json={"title": "t", "body": "b"}, headers=b1).status_code == 403

    # 3) 열람 신청 → 관리자 승인 → 기간 동안 읽기만
    r = client.post(f"/api/community/{va}/access-requests", json={"reason": "공동 고객사 장애 분석", "days": 7}, headers=b1)
    assert r.status_code == 201
    grant_id = r.json()["id"]
    assert client.post(f"/api/community/{va}/access-requests", json={"reason": "중복"}, headers=b1).status_code == 409
    assert client.post(f"/api/community/{vendor_b['id']}/access-requests", json={"reason": "x"}, headers=b1).status_code == 400
    assert client.post(f"/api/admin/access-requests/{grant_id}/decision", json={"approve": True}, headers=a1).status_code == 403

    pending = client.get("/api/admin/access-requests", params={"status": "pending"}, headers=admin).json()
    assert [g["id"] for g in pending] == [grant_id] and pending[0]["user"]["partner_name"] == "커뮤B1"
    r = client.post(f"/api/admin/access-requests/{grant_id}/decision", json={"approve": True, "days": 3, "note": "3일만 허용"}, headers=admin)
    assert r.json()["active"] and r.json()["decided_by_name"] == "관리자"

    assert len(client.get(f"/api/community/{va}/posts", headers=b1).json()) == 1
    detail = client.get(f"/api/community/posts/{post['id']}", headers=b1).json()
    assert detail["can_write"] is False
    assert client.post(f"/api/community/posts/{post['id']}/comments", json={"body": "참고"}, headers=b1).status_code == 403
    assert client.post(f"/api/community/{va}/events", json={"title": "t", "starts_at": starts.isoformat()}, headers=b1).status_code == 403
    assert client.post(f"/api/community/events/{event['id']}/rsvp", headers=b1).status_code == 200  # 세션 참석은 가능
    assert {d["vendor_name"]: d["access"] for d in client.get("/api/community/domains", headers=b1).json()}["CommVendorA"] == "granted"

    # 4) 기간 만료 → 다시 차단
    with SessionLocal() as db:
        grant = db.get(AccessGrant, grant_id)
        grant.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert client.get(f"/api/community/{va}/posts", headers=b1).status_code == 403

    # 5) 재신청 → 승인 → 관리자 회수 → 차단, 이력은 모두 남는다
    grant2 = client.post(f"/api/community/{va}/access-requests", json={"reason": "재신청"}, headers=b1).json()["id"]
    client.post(f"/api/admin/access-requests/{grant2}/decision", json={"approve": True}, headers=admin)
    assert client.get(f"/api/community/{va}/posts", headers=b1).status_code == 200
    assert client.post(f"/api/admin/access-requests/{grant2}/revoke", headers=admin).json()["status"] == "revoked"
    assert client.get(f"/api/community/{va}/posts", headers=b1).status_code == 403
    mine = client.get("/api/community/access-requests/mine", headers=b1).json()
    assert [g["status"] for g in mine] == ["revoked", "approved"] and not any(g["active"] for g in mine)

    # 거절
    grant3 = client.post(f"/api/community/{va}/access-requests", json={"reason": "또"}, headers=b1).json()["id"]
    r = client.post(f"/api/admin/access-requests/{grant3}/decision", json={"approve": False, "note": "필요성 부족"}, headers=admin)
    assert r.json()["status"] == "rejected" and r.json()["decision_note"] == "필요성 부족"

    # 6) 정식 소속 부여: 신청자의 파트너사 전체가 도메인 소속이 되고, 회수하면 빠진다.
    b1_colleague = _signup_and_approve(client, admin, "b1-2@comm.example.com", _partner_id(client, admin, "커뮤B1"))
    grant4 = client.post(f"/api/community/{va}/access-requests", json={"reason": "A 벤더 신규 지원 시작"}, headers=b1).json()["id"]
    r = client.post(f"/api/admin/access-requests/{grant4}/decision", json={"approve": True, "grant_type": "member"}, headers=admin)
    assert r.json()["grant_type"] == "member" and r.json()["active"] and r.json()["expires_at"] is None
    for who in (b1, b1_colleague):
        assert {d["vendor_name"]: d["access"] for d in client.get("/api/community/domains", headers=who).json()}["CommVendorA"] == "member"
    assert client.post(f"/api/community/{va}/posts", json={"title": "B1 첫 글", "body": "이제 쓸 수 있음"}, headers=b1_colleague).status_code == 201
    assert va in [v["id"] for v in client.get("/api/vendors", headers=b1).json()]  # 문서 업로드 도메인에도 나타남
    assert client.post(f"/api/admin/access-requests/{grant4}/revoke", headers=admin).json()["active"] is False
    assert client.get(f"/api/community/{va}/posts", headers=b1_colleague).status_code == 403

    # 7) 글 삭제는 작성자(또는 관리자)만, 해결 댓글 삭제 시 지정 해제
    assert client.delete(f"/api/community/comments/{comment_id}", headers=a1).status_code == 403
    assert client.delete(f"/api/community/comments/{comment_id}", headers=a2).status_code == 204
    assert client.get(f"/api/community/posts/{post['id']}", headers=a1).json()["solution_comment_id"] is None
    assert client.delete(f"/api/community/posts/{post['id']}", headers=a2).status_code == 403
    assert client.delete(f"/api/community/posts/{post['id']}", headers=a1).status_code == 204
