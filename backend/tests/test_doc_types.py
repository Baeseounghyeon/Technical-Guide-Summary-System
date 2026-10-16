"""문서 종류(규격서·기술 가이드·브로슈어): 등록할 때 고르고, 종류·벤더별로 목록을 본다."""

from pathlib import Path

from app.worker import run_pending_jobs

from .conftest import ADMIN, login
from .test_flow import _make_vendor_docx, _partner_with_vendor, _signup_and_approve


def _grant(client, admin, user, scopes: list[str]) -> None:
    """권한 승인 요청 → 관리자 승인으로 업무 밖 권한을 더한다."""
    me = client.get("/api/auth/me", headers=user).json()
    r = client.post("/api/permission-requests", json={"scopes": scopes, "reason": "테스트", "name": me["name"], "email": me["email"]}, headers=user)
    assert r.status_code == 201, r.text
    client.post(f"/api/admin/permission-requests/{r.json()['id']}/decision", json={"approve": True}, headers=admin)


def test_documents_by_type_and_vendor(client, tmp_path: Path):
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "종류파트너", "TypeVendorA")
    _, vendor_b = _partner_with_vendor(client, admin, "종류파트너B", "TypeVendorB")
    client.put(f"/api/admin/partners/{partner['id']}/vendors", json={"vendor_ids": [vendor["id"], vendor_b["id"]]}, headers=admin)
    user = _signup_and_approve(client, admin, "types@t.example.com", partner["id"])
    _grant(client, admin, user, ["spec"])  # 엔지니어는 기본으로 규격서를 올릴 수 없다
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


def test_guide_kinds(client, tmp_path: Path):
    """기술 가이드 문서는 기술 가이드 / 트러블 슈팅 가이드로 나뉜다 (가이드 화면의 종류 선택)."""
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "가이드종류파트너", "KindVendor")
    user = _signup_and_approve(client, admin, "kinds@k.example.com", partner["id"])
    src = tmp_path / "v.docx"
    _make_vendor_docx(src)
    for title, kind in [("설치 가이드", "technical"), ("장애 대응", "troubleshooting"), ("기본값", None)]:
        data = {"vendor_id": vendor["id"], "doc_type": "guide", "title": title}
        if kind:
            data["guide_kind"] = kind
        with src.open("rb") as f:
            assert client.post("/api/documents", data=data, files={"file": ("v.docx", f)}, headers=user).status_code == 201
    with src.open("rb") as f:
        spec = client.post(
            "/api/documents", data={"vendor_id": vendor["id"], "doc_type": "brochure", "guide_kind": "troubleshooting", "title": "브로슈어"},
            files={"file": ("v.docx", f)}, headers=user,
        ).json()
    assert spec["guide_kind"] is None  # 가이드가 아닌 문서에는 종류가 없다
    run_pending_jobs()

    def titles(query: str) -> list[str]:
        return sorted(d["title"] for d in client.get(f"/api/documents?doc_type=guide&vendor_id={vendor['id']}{query}", headers=user).json())

    assert titles("") == ["기본값", "설치 가이드", "장애 대응"]
    assert titles("&guide_kind=technical") == ["기본값", "설치 가이드"]
    assert titles("&guide_kind=troubleshooting") == ["장애 대응"]


def test_download_formats_delete_and_filters(client, tmp_path: Path):
    """원본·Word·PPT·Excel·PDF 내려받기, 파트너·작성자 필터, 관리자 삭제."""
    import io

    import pymupdf
    from docx import Document
    from openpyxl import load_workbook

    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "다운로드파트너", "DownloadVendor")
    user = _signup_and_approve(client, admin, "dl@d.example.com", partner["id"])
    src = tmp_path / "v.docx"
    _make_vendor_docx(src)
    with src.open("rb") as f:
        doc = client.post("/api/documents", data={"vendor_id": vendor["id"], "title": "다운로드 가이드"}, files={"file": ("v.docx", f)}, headers=user).json()
    run_pending_jobs()
    base = f"/api/documents/{doc['id']}/download"

    assert client.get(f"{base}?format=original", headers=user).content == src.read_bytes()
    word = Document(io.BytesIO(client.get(f"{base}?format=docx", headers=user).content))
    assert "Install steps" in "\n".join(p.text for p in word.paragraphs)
    assert client.get(f"{base}?format=pptx", headers=user).content[:2] == b"PK"
    sheet = load_workbook(io.BytesIO(client.get(f"{base}?format=xlsx", headers=user).content)).active
    assert sheet["C1"].value == "목차" and any(r[2] == "Install steps" for r in sheet.iter_rows(values_only=True))
    r = client.get(f"{base}?format=pdf", headers=user)
    assert "attachment" in r.headers["content-disposition"]
    assert "Install steps" in "".join(p.get_text() for p in pymupdf.open("pdf", r.content))
    assert client.get(f"{base}?format=exe", headers=user).status_code == 422

    # 파트너·작성자 필터
    me_id = client.get("/api/auth/me", headers=user).json()["id"]
    listed = client.get(f"/api/documents?doc_type=guide&partner_id={partner['id']}&uploaded_by={me_id}", headers=admin).json()
    assert [d["id"] for d in listed] == [doc["id"]] and listed[0]["partner_name"] == "다운로드파트너"
    assert client.get(f"/api/documents?uploaded_by={me_id + 999}", headers=admin).json() == []

    # 삭제는 올린 사람 또는 플랫폼 관리자만 (같은 회사 동료는 불가)
    coworker = _signup_and_approve(client, admin, "dl2@d.example.com", partner["id"])
    assert client.delete(f"/api/documents/{doc['id']}", headers=coworker).status_code == 403
    assert client.delete(f"/api/documents/{doc['id']}", headers=admin).status_code == 204
    assert client.get(f"/api/documents/{doc['id']}", headers=admin).status_code == 404



def test_share_and_domain_access(client, tmp_path: Path):
    """가이드 공유(다른 조직 체크 → 읽기 가능), 도메인 권한 승인 → 그 벤더의 다른 조직 문서 열람, 읽기 전용."""
    admin = login(client, *ADMIN)
    owner_partner, vendor = _partner_with_vendor(client, admin, "공유원본사", "DocShareVendor")
    other_partner, _ = _partner_with_vendor(client, admin, "공유받는사", "DocShareOtherVendor")
    third_partner, _ = _partner_with_vendor(client, admin, "제3사", "DocShareThirdVendor")
    owner = _signup_and_approve(client, admin, "share-o@s.example.com", owner_partner["id"])
    other = _signup_and_approve(client, admin, "share-x@s.example.com", other_partner["id"])
    third = _signup_and_approve(client, admin, "share-t@s.example.com", third_partner["id"])
    src = tmp_path / "v.docx"
    _make_vendor_docx(src)
    with src.open("rb") as f:
        doc = client.post("/api/documents", data={"vendor_id": vendor["id"], "title": "공유 가이드"}, files={"file": ("v.docx", f)}, headers=owner).json()
    run_pending_jobs()

    # 공유 전에는 다른 조직이 볼 수 없다
    assert client.get(f"/api/documents/{doc['id']}", headers=other).status_code == 404
    orgs = client.get("/api/organizations", headers=owner).json()
    assert {"공유받는사", "제3사"} <= {o["name"] for o in orgs}
    # 공유 범위는 올린 사람만 정한다
    assert client.put(f"/api/documents/{doc['id']}/shares", json={"partner_ids": [other_partner["id"]]}, headers=other).status_code == 404
    r = client.put(f"/api/documents/{doc['id']}/shares", json={"partner_ids": [other_partner["id"], third_partner["id"]]}, headers=owner)
    assert r.json()["shared_with"] == ["공유받는사", "제3사"]
    # 공유받은 조직: 목록·상세·다운로드는 되지만 요약·삭제는 안 된다 (읽기 전용)
    mine = client.get("/api/documents?shared_to_me=true", headers=other).json()
    assert [d["id"] for d in mine] == [doc["id"]] and mine[0]["access"] == "shared"
    assert client.get(f"/api/documents/{doc['id']}/download?format=original", headers=other).status_code == 200
    assert client.post(f"/api/documents/{doc['id']}/guides", json={"target_language": "ko"}, headers=other).status_code == 404
    assert client.delete(f"/api/documents/{doc['id']}", headers=other).status_code == 403
    # 공유를 하나 빼면 그 조직은 다시 못 본다
    client.put(f"/api/documents/{doc['id']}/shares", json={"partner_ids": [other_partner["id"]]}, headers=owner)
    assert client.get(f"/api/documents/{doc['id']}", headers=third).status_code == 404

    # 도메인 권한 요청(신청자 정보 포함) → 관리자 승인 → 그 벤더의 다른 조직 문서 열람
    r = client.post(
        f"/api/community/{vendor['id']}/access-requests",
        json={"reason": "고객 제안 검토", "request_date": "2026-10-20", "requester_name": "제3 담당", "requester_company": "제3사"},
        headers=third,
    )
    assert r.status_code == 201 and r.json()["request_date"] == "2026-10-20" and r.json()["requester_name"] == "제3 담당"
    assert r.json()["requester_email"] == "share-t@s.example.com"  # 비우면 가입 정보로
    client.post(f"/api/admin/access-requests/{r.json()['id']}/decision", json={"approve": True, "grant_type": "read", "days": 30}, headers=admin)
    listed = client.get(f"/api/documents?vendor_id={vendor['id']}", headers=third).json()
    assert [d["id"] for d in listed] == [doc["id"]] and listed[0]["access"] == "domain"
    assert client.get(f"/api/documents/{doc['id']}", headers=third).status_code == 200

    # 올린 사람은 직접 삭제할 수 있다
    assert client.delete(f"/api/documents/{doc['id']}", headers=owner).status_code == 204



def test_track_permissions_and_admin_user_edit(client, tmp_path: Path):
    """업무 구분별 권한(엔지니어/영업), 권한 승인 요청, 관리자의 가입자 정보·도메인 수정."""
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "권한파트너", "PermVendor")
    _, other_vendor = _partner_with_vendor(client, admin, "권한다른파트너", "PermOtherVendor")
    engineer = _signup_and_approve(client, admin, "perm-e@p.example.com", partner["id"])
    r = client.post("/api/auth/signup", json={"email": "perm-s@p.example.com", "password": "sales-pass-1", "name": "영업", "company_name": "권한파트너", "track": "sales"})
    client.post(f"/api/admin/users/{r.json()['id']}/approve", json={"partner_id": partner["id"], "role": "engineer"}, headers=admin)
    sales = login(client, "perm-s@p.example.com", "sales-pass-1")
    src = tmp_path / "v.docx"
    _make_vendor_docx(src)

    def upload(who, doc_type):
        with src.open("rb") as f:
            return client.post("/api/documents", data={"vendor_id": vendor["id"], "doc_type": doc_type, "title": f"{doc_type} 문서"}, files={"file": ("v.docx", f)}, headers=who)

    assert sorted(client.get("/api/auth/me", headers=engineer).json()["permissions"]) == ["brochure", "guide"]
    assert sorted(client.get("/api/auth/me", headers=sales).json()["permissions"]) == ["brochure", "quote", "spec"]
    assert upload(engineer, "spec").status_code == 403 and upload(sales, "guide").status_code == 403
    assert upload(sales, "brochure").status_code == 201
    guide_doc = upload(engineer, "guide").json()
    run_pending_jobs()
    # 영업은 가이드를 내려받을 수는 있지만 요약은 못 한다
    assert client.get(f"/api/documents/{guide_doc['id']}/download?format=original", headers=sales).status_code == 200
    assert client.post(f"/api/documents/{guide_doc['id']}/guides", json={"target_language": "ko"}, headers=sales).status_code == 403

    # 권한 승인 요청 → 승인되면 영업도 가이드 요약 가능, 반려(회수)하면 다시 막힘
    me = client.get("/api/auth/me", headers=sales).json()
    assert client.post("/api/permission-requests", json={"scopes": ["spec"], "reason": "x", "name": "a", "email": "a@a.a"}, headers=sales).status_code == 400
    r = client.post("/api/permission-requests", json={"scopes": ["guide"], "reason": "기술 지원 겸업", "name": "영업 담당", "email": me["email"], "phone": "010-1"}, headers=sales)
    assert r.status_code == 201 and r.json()["scope_labels"] == ["가이드 등록·요약"] and r.json()["name"] == "영업 담당"
    assert client.post("/api/permission-requests", json={"scopes": ["guide"], "reason": "중복", "name": "a", "email": "a@a.a"}, headers=sales).status_code == 409
    pending = client.get("/api/admin/permission-requests?status=pending", headers=admin).json()
    assert [p["id"] for p in pending if p["user_id"] == me["id"]] == [r.json()["id"]]
    client.post(f"/api/admin/permission-requests/{r.json()['id']}/decision", json={"approve": True, "note": "승인"}, headers=admin)
    assert "guide" in client.get("/api/auth/me", headers=sales).json()["permissions"]
    assert client.post(f"/api/documents/{guide_doc['id']}/guides", json={"target_language": "en"}, headers=sales).status_code == 201
    client.post(f"/api/admin/permission-requests/{r.json()['id']}/decision", json={"approve": False, "note": "회수"}, headers=admin)
    assert client.get("/api/permission-requests/mine", headers=sales).json()[0]["status"] == "revoked"
    assert "guide" not in client.get("/api/auth/me", headers=sales).json()["permissions"]
    run_pending_jobs()

    # 관리자: 가입자 정보 수정 (이메일 중복 불가)
    eng_id = client.get("/api/auth/me", headers=engineer).json()["id"]
    r = client.put(f"/api/admin/users/{eng_id}/profile", json={"name": "새 이름", "company_name": "새 회사", "email": "Perm-E2@p.example.com", "phone": "010-9"}, headers=admin)
    assert r.json()["name"] == "새 이름" and r.json()["email"] == "perm-e2@p.example.com"
    assert client.put(f"/api/admin/users/{eng_id}/profile", json={"name": "x", "email": "perm-s@p.example.com"}, headers=admin).status_code == 409
    assert login(client, "perm-e2@p.example.com", "engineer-pass-1")  # 바뀐 이메일로 로그인

    # 관리자: 사용자별 도메인 지정 → 파트너사 기본 대신 지정한 것만
    r = client.put(f"/api/admin/users/{eng_id}/domains", json={"vendor_ids": [other_vendor["id"]]}, headers=admin)
    assert r.json() == {"custom_domains": True, "domains": ["PermOtherVendor"]}
    row = next(u for u in client.get("/api/admin/users", headers=admin).json() if u["id"] == eng_id)
    assert row["custom_domains"] and row["domains"] == ["PermOtherVendor"]
    r = client.put(f"/api/admin/users/{eng_id}/domains", json={"use_partner_default": True}, headers=admin)
    assert r.json() == {"custom_domains": False, "domains": ["PermVendor"]}
