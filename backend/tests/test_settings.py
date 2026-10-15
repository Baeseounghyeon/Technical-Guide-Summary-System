"""설정 화면이 쓰는 API: 파트너사 자산(로고 미리보기 포함)과 벤더 용어집 권한."""

import io

from PIL import Image

from .conftest import ADMIN, login
from .test_flow import _partner_with_vendor, _signup_and_approve


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (60, 20), "teal").save(buf, format="PNG")
    return buf.getvalue()


def test_partner_logo_and_assets(client):
    admin = login(client, *ADMIN)
    partner, _ = _partner_with_vendor(client, admin, "설정파트너", "SettingsVendor")
    other_partner, _ = _partner_with_vendor(client, admin, "설정파트너2", "SettingsVendor2")
    owner = _signup_and_approve(client, admin, "padmin@settings.example.com", partner["id"], role="partner_admin")
    engineer = _signup_and_approve(client, admin, "eng@settings.example.com", partner["id"])
    outsider = _signup_and_approve(client, admin, "padmin@settings2.example.com", other_partner["id"], role="partner_admin")
    logo_url = f"/api/partners/{partner['id']}/logo"

    assert client.get(logo_url, headers=owner).status_code == 404  # 아직 로고 없음

    png = _png()
    r = client.post(f"/api/partners/{partner['id']}/assets/logo", files={"file": ("logo.png", png, "image/png")}, headers=owner)
    assert r.status_code == 200, r.text
    assert r.json()["logo_path"]

    for viewer in (owner, engineer, admin):
        r = client.get(logo_url, headers=viewer)
        assert r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content == png
    # 다른 파트너사는 로고 존재 여부도 알 수 없다.
    assert client.get(logo_url, headers=outsider).status_code == 404
    assert client.get(logo_url).status_code == 401

    # 엔지니어는 볼 수만 있고 바꿀 수 없다. 형식이 맞지 않으면 거절한다.
    r = client.post(f"/api/partners/{partner['id']}/assets/logo", files={"file": ("logo.png", png, "image/png")}, headers=engineer)
    assert r.status_code == 403
    r = client.post(f"/api/partners/{partner['id']}/assets/docx_template", files={"file": ("t.pdf", b"x")}, headers=owner)
    assert r.status_code == 400
    r = client.post(f"/api/partners/{partner['id']}/assets/docx_template", files={"file": ("t.dotx", b"PK")}, headers=admin)
    assert r.status_code == 200 and r.json()["docx_template_path"].endswith(".dotx")


def test_glossary_permissions(client):
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "용어집파트너", "GlossaryVendor")
    owner = _signup_and_approve(client, admin, "padmin@glossary.example.com", partner["id"], role="partner_admin")
    engineer = _signup_and_approve(client, admin, "eng@glossary.example.com", partner["id"])
    url = f"/api/vendors/{vendor['id']}/glossary"

    term = {"target_language": "ko", "source_term": "Access Point", "target_term": "액세스 포인트"}
    assert client.put(url, json=term, headers=owner).status_code == 200
    assert client.put(url, json={**term, "target_term": "AP"}, headers=owner).json()["target_term"] == "AP"  # 같은 원어는 수정
    assert client.put(url, json={**term, "target_language": "ja", "target_term": "アクセスポイント"}, headers=admin).status_code == 200
    assert client.put(url, json=term, headers=engineer).status_code == 403

    ko = client.get(url, params={"target_language": "ko"}, headers=engineer).json()
    assert [(t["source_term"], t["target_term"]) for t in ko] == [("Access Point", "AP")]
    assert len(client.get(url, headers=engineer).json()) == 2
