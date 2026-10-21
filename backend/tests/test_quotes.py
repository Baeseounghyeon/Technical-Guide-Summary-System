"""영업(견적서): 업무 구분, 참고 자료 관리와 접근 제한."""

import io

from .conftest import ADMIN, login
from .test_flow import _partner_with_vendor, _signup_and_approve


def _signup_sales(client, admin, email: str, partner_id: int, role: str = "engineer") -> dict:
    r = client.post(
        "/api/auth/signup",
        json={"email": email, "password": "sales-pass-1", "name": "영업 담당", "company_name": "영업사", "track": "sales"},
    )
    assert r.status_code == 201, r.text
    user_id = r.json()["id"]
    r = client.post(f"/api/admin/users/{user_id}/approve", json={"partner_id": partner_id, "role": role}, headers=admin)
    assert r.json()["track"] == "sales"  # 가입 때 고른 구분이 유지된다
    return login(client, email, "sales-pass-1")


def test_sales_track_and_quote_files(client):
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "영업파트너", "QuoteVendor")
    sales = _signup_sales(client, admin, "sales@s.example.com", partner["id"], role="partner_admin")
    engineer = _signup_and_approve(client, admin, "eng@s.example.com", partner["id"])

    assert client.get("/api/auth/me", headers=sales).json()["track"] == "sales"
    # 엔지니어는 견적 자료를 내려받기만 (올리기 불가)
    assert client.get("/api/quote-files", headers=engineer).status_code == 200
    assert client.post("/api/quote-files", files={"file": ("a.pdf", b"%PDF")}, headers=engineer).status_code == 403

    # 회사별 견적서 양식·로고는 삭제됨 (견적서 양식은 견적서 생성 > 견적서 양식, 로고는 양식 엑셀 안에)
    for kind in ("quote_template", "quote_logo"):
        r = client.post(f"/api/partners/{partner['id']}/assets/{kind}", files={"file": ("logo.png", b"PNG", "image/png")}, headers=sales)
        assert r.status_code == 422

    # 참고 자료: 업로드 → 목록 → 받기 → 삭제
    r = client.post(
        "/api/quote-files",
        data={"category": "spec", "vendor_id": vendor["id"], "note": "2026 규격서"},
        files={"file": ("규격서.pdf", io.BytesIO(b"%PDF-1.4 spec"), "application/pdf")},
        headers=sales,
    )
    assert r.status_code == 201, r.text
    f = r.json()
    assert f["filename"] == "규격서.pdf" and f["vendor_name"] == "QuoteVendor" and f["category"] == "spec"
    assert [x["id"] for x in client.get("/api/quote-files", headers=sales).json()] == [f["id"]]
    assert client.get(f"/api/quote-files/{f['id']}/download", headers=sales).content == b"%PDF-1.4 spec"
    assert client.post("/api/quote-files", files={"file": ("a.exe", b"MZ")}, headers=sales).status_code == 400

    # 다른 회사 영업 사용자는 볼 수 없다
    other_partner, _ = _partner_with_vendor(client, admin, "다른영업사", "OtherQuoteVendor")
    other = _signup_sales(client, admin, "sales2@s.example.com", other_partner["id"])
    assert client.get("/api/quote-files", headers=other).json() == []
    assert client.get(f"/api/quote-files/{f['id']}/download", headers=other).status_code == 404

    # 관리자는 업무 구분을 바꿀 수 있다
    me_id = client.get("/api/auth/me", headers=engineer).json()["id"]
    r = client.post(f"/api/admin/users/{me_id}/approve", json={"partner_id": partner["id"], "role": "engineer", "track": "sales"}, headers=admin)
    assert r.json()["track"] == "sales"
    assert client.get("/api/quote-files", headers=engineer).status_code == 200

    assert client.delete(f"/api/quote-files/{f['id']}", headers=sales).status_code == 204
    assert client.get("/api/quote-files", headers=sales).json() == []
