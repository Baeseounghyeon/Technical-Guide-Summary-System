"""홈 달력: 개인 일정 추가·조회(기간 겹침)·수정·삭제, 본인 일정만."""

from .conftest import ADMIN, login
from .test_flow import _partner_with_vendor, _signup_and_approve


def test_personal_events(client):
    admin = login(client, *ADMIN)
    partner, _ = _partner_with_vendor(client, admin, "달력파트너", "CalendarVendor")
    user = _signup_and_approve(client, admin, "cal@c.example.com", partner["id"])
    other = _signup_and_approve(client, admin, "cal2@c.example.com", partner["id"])

    r = client.post(
        "/api/calendar/events",
        json={"title": "SK쉴더스 CM 제안 미팅", "purpose": "meeting", "start_date": "2026-10-16", "end_date": "2026-10-16",
              "start_time": "13:00", "end_time": "18:00", "content": "제안서 검토"},
        headers=user,
    )
    assert r.status_code == 201, r.text
    meeting = r.json()
    trip = client.post(
        "/api/calendar/events",
        json={"title": "부산 외근", "purpose": "outside", "start_date": "2026-10-30", "end_date": "2026-11-02"},
        headers=user,
    ).json()

    def titles(start: str, end: str, who=user) -> list[str]:
        return [e["title"] for e in client.get(f"/api/calendar/events?start={start}&end={end}", headers=who).json()]

    assert titles("2026-10-01", "2026-10-31") == ["SK쉴더스 CM 제안 미팅", "부산 외근"]
    assert titles("2026-11-01", "2026-11-30") == ["부산 외근"]  # 이어지는 일정은 다음 달에도 보인다
    assert titles("2026-10-01", "2026-10-31", other) == []  # 다른 사람 일정은 안 보인다

    # 잘못된 입력
    bad = {"title": "x", "purpose": "meeting", "start_date": "2026-10-20", "end_date": "2026-10-19"}
    assert client.post("/api/calendar/events", json=bad, headers=user).status_code == 422
    assert client.post("/api/calendar/events", json={**bad, "end_date": "2026-10-20", "start_time": "25:00"}, headers=user).status_code == 422
    assert client.post("/api/calendar/events", json={**bad, "end_date": "2026-10-20", "purpose": "party"}, headers=user).status_code == 422

    r = client.put(f"/api/calendar/events/{trip['id']}", json={**trip, "purpose": "vacation", "title": "휴가"}, headers=user)
    assert r.json()["purpose"] == "vacation" and r.json()["title"] == "휴가"
    assert client.put(f"/api/calendar/events/{trip['id']}", json={**trip}, headers=other).status_code == 404
    assert client.delete(f"/api/calendar/events/{meeting['id']}", headers=other).status_code == 404
    assert client.delete(f"/api/calendar/events/{meeting['id']}", headers=user).status_code == 204
    assert titles("2026-10-01", "2026-10-31") == ["휴가"]


def test_my_requests_and_org_guides(client, tmp_path):
    """내 요청 사항(내가 요청한 요약)과 조직 요청 가이드(같은 회사), 다른 회사는 안 보임."""
    from app.worker import run_pending_jobs

    from .test_flow import _make_vendor_docx

    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "요청파트너", "RequestVendor")
    other_partner, _ = _partner_with_vendor(client, admin, "다른요청파트너", "OtherRequestVendor")
    a = _signup_and_approve(client, admin, "req-a@r.example.com", partner["id"])
    b = _signup_and_approve(client, admin, "req-b@r.example.com", partner["id"])
    outsider = _signup_and_approve(client, admin, "req-x@r.example.com", other_partner["id"])
    src = tmp_path / "v.docx"
    _make_vendor_docx(src)
    with src.open("rb") as f:
        doc_id = client.post("/api/documents", data={"vendor_id": vendor["id"], "title": "요청 문서"}, files={"file": ("v.docx", f)}, headers=a).json()["id"]
    run_pending_jobs()
    guide_id = client.post(f"/api/documents/{doc_id}/guides", json={"target_language": "ko"}, headers=a).json()["id"]
    run_pending_jobs()

    mine = client.get("/api/my-requests", headers=a).json()
    assert [r["guide_id"] for r in mine] == [guide_id] and mine[0]["total"] == 3 and mine[0]["document_title"] == "요청 문서"
    assert client.get("/api/my-requests", headers=b).json() == []
    org = client.get("/api/org-guides", headers=b).json()  # 같은 회사 동료에게 보인다
    assert [r["guide_id"] for r in org] == [guide_id] and org[0]["requested_by_name"] and org[0]["exports"] == []
    assert client.get("/api/org-guides", headers=outsider).json() == []
