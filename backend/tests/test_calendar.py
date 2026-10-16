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
