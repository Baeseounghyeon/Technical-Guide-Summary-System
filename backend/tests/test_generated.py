"""규격서·견적서 생성: 등록한 규격서를 재사용해 필수 입력값을 채우고, 고쳐서 새로 만들고, 버전 이력이 쌓인다.
업무 구분: 규격서·견적서 생성은 영업만(관리자 포함), 엔지니어는 불가."""

from pathlib import Path

from docx import Document

from app.worker import run_pending_jobs

from .conftest import ADMIN, login
from .test_flow import _partner_with_vendor, _signup_and_approve


def _spec_docx(path: Path) -> None:
    d = Document()
    d.add_heading("테스트 규격서", 0)
    for label, text in [("항목 A", "Luna HSM"), ("항목 B", "Luna 7 A790"), ("항목 C", "2대"), ("항목 D", "본사 전산실"), ("항목 E", "FIPS 140-3 Level 3 인증")]:
        d.add_heading(label, 1)
        d.add_paragraph(text)
    d.save(str(path))


def test_spec_generation_reuse_and_versions(client, tmp_path: Path):
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "생성파트너", "GenVendor")
    sales = _signup_and_approve(client, admin, "gen-sales@g.example.com", partner["id"])
    sales_id = client.get("/api/auth/me", headers=sales).json()["id"]
    client.post(f"/api/admin/users/{sales_id}/approve", json={"partner_id": partner["id"], "track": "sales"}, headers=admin)
    engineer = _signup_and_approve(client, admin, "gen-eng@g.example.com", partner["id"])

    src = tmp_path / "spec.docx"
    _spec_docx(src)
    with src.open("rb") as f:
        doc = client.post(
            "/api/documents", data={"vendor_id": vendor["id"], "doc_type": "spec", "title": "테스트 규격서"},
            files={"file": ("spec.docx", f)}, headers=sales,
        ).json()
    run_pending_jobs()

    fields = client.get("/api/forms/spec/fields", headers=sales).json()
    assert [f["key"] for f in fields] == ["a", "b", "c", "d", "e"]

    # 재사용: 등록한 규격서의 내용이 필수 입력값에 채워진다
    filled = client.get(f"/api/forms/spec/prefill?document_id={doc['id']}", headers=sales).json()
    assert filled["fields"] == {"a": "Luna HSM", "b": "Luna 7 A790", "c": "2대", "d": "본사 전산실", "e": "FIPS 140-3 Level 3 인증"}
    assert client.get(f"/api/forms/spec/prefill?document_id={doc['id']}", headers=engineer).status_code == 403

    # 미리보기는 PDF
    body = {"doc_type": "spec", "title": "새 규격서", "fields": filled["fields"], "source_document_id": doc["id"]}
    r = client.post("/api/forms/preview", json=body, headers=sales)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")

    # 필수값이 비면 생성 불가, 엔지니어도 불가
    assert client.post("/api/generated", json={**body, "fields": {**filled["fields"], "c": ""}}, headers=sales).status_code == 400
    assert client.post("/api/generated", json=body, headers=engineer).status_code == 403

    # 고쳐서 생성 → v1, 다시 고쳐서 → v2 (같은 이력)
    v1 = client.post("/api/generated", json={**body, "fields": {**filled["fields"], "c": "3대"}}, headers=sales).json()
    assert v1["version"] == 1 and v1["fields"]["c"] == "3대" and v1["source_document_title"] == "테스트 규격서"
    v2 = client.post("/api/generated", json={**body, "fields": {**v1["fields"], "c": "4대"}, "based_on_id": v1["id"]}, headers=sales).json()
    assert v2["version"] == 2 and v2["root_id"] == v1["id"] and v2["based_on_id"] == v1["id"]

    rows = client.get("/api/generated?doc_type=spec", headers=sales).json()
    assert [(g["version"], g["fields"]["c"]) for g in rows] == [(2, "4대"), (1, "3대")]
    assert client.get("/api/generated?doc_type=quote", headers=sales).json() == []

    for fmt, magic in [("pdf", b"%PDF"), ("docx", b"PK")]:
        r = client.get(f"/api/generated/{v2['id']}/download?format={fmt}", headers=sales)
        assert r.status_code == 200 and r.content.startswith(magic)

    # 견적서도 같은 방식
    q = client.post("/api/generated", json={**body, "doc_type": "quote", "title": "견적서"}, headers=sales)
    assert q.status_code == 201 and q.json()["doc_type"] == "quote"


def test_my_guides_lists_created_guides(client):
    admin = login(client, *ADMIN)
    assert isinstance(client.get("/api/my-guides", headers=admin).json(), list)


def _xlsx(path: Path, rows: list[tuple]) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "규격"
    for r in rows:
        ws.append(list(r))
    wb.save(str(path))


def test_excel_spec_and_extra_documents(client, tmp_path: Path):
    """규격서는 Excel 로도 등록되고, 기타 문서(제품 가격표·매입 금액)는 PDF·Word·Excel 만 받아 규격서 생성 때 첨부한다."""
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "기타문서파트너", "ExtraVendor")
    sales = _signup_and_approve(client, admin, "extra-sales@x.example.com", partner["id"])
    sales_id = client.get("/api/auth/me", headers=sales).json()["id"]
    client.post(f"/api/admin/users/{sales_id}/approve", json={"partner_id": partner["id"], "track": "sales"}, headers=admin)
    engineer = _signup_and_approve(client, admin, "extra-eng@x.example.com", partner["id"])

    def upload(headers, name: str, data: dict):
        with (tmp_path / name).open("rb") as f:
            return client.post("/api/documents", data={"vendor_id": vendor["id"], **data}, files={"file": (name, f)}, headers=headers)

    # Excel 규격서: '항목 | 값' 행이 필수 입력값으로 채워진다
    _xlsx(tmp_path / "spec.xlsx", [("항목 A", "Luna HSM"), ("항목 B", "A790"), ("항목 C", "2대"), ("항목 D", "본사"), ("항목 E", "FIPS 140-3")])
    r = upload(sales, "spec.xlsx", {"doc_type": "spec", "title": "엑셀 규격서"})
    assert r.status_code == 201, r.text
    spec = r.json()
    assert spec["source_type"] == "xlsx"
    # Excel 은 규격서·기타 문서만
    assert upload(sales, "spec.xlsx", {"doc_type": "brochure"}).status_code == 400

    # 기타 문서: 종류 필수, 엔지니어 불가, PowerPoint 불가
    _xlsx(tmp_path / "price.xlsx", [("제품", "단가"), ("Luna HSM", "30,000,000")])
    assert upload(sales, "price.xlsx", {"doc_type": "spec_extra"}).status_code == 400
    assert upload(engineer, "price.xlsx", {"doc_type": "spec_extra", "extra_kind": "price_list"}).status_code == 403
    price = upload(sales, "price.xlsx", {"doc_type": "spec_extra", "extra_kind": "price_list", "title": "가격표"}).json()
    purchase = upload(sales, "price.xlsx", {"doc_type": "spec_extra", "extra_kind": "purchase", "title": "매입가"}).json()
    run_pending_jobs()

    filled = client.get(f"/api/forms/spec/prefill?document_id={spec['id']}", headers=sales).json()
    assert filled["fields"] == {"a": "Luna HSM", "b": "A790", "c": "2대", "d": "본사", "e": "FIPS 140-3"}

    lists = {k: [d["title"] for d in client.get(f"/api/documents?doc_type=spec_extra&extra_kind={k}", headers=sales).json()] for k in ("price_list", "purchase")}
    assert lists == {"price_list": ["가격표"], "purchase": ["매입가"]}
    # 기타 문서는 규격서 목록에 섞이지 않는다
    assert [d["title"] for d in client.get("/api/documents?doc_type=spec", headers=sales).json()] == ["엑셀 규격서"]

    body = {"doc_type": "spec", "title": "첨부 규격서", "fields": filled["fields"], "source_document_id": spec["id"]}
    # 종류가 맞지 않으면 거절
    assert client.post("/api/generated", json={**body, "attachments": {"price_list": purchase["id"]}}, headers=sales).status_code == 400
    g = client.post("/api/generated", json={**body, "attachments": {"price_list": price["id"], "purchase": purchase["id"]}}, headers=sales).json()
    assert [(a["label"], a["title"]) for a in g["attachments"]] == [("제품 가격표", "가격표"), ("매입 금액", "매입가")]
    r = client.post("/api/forms/preview", json={**body, "attachments": {"price_list": price["id"]}}, headers=sales)
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    for fmt in ("pdf", "docx"):
        assert client.get(f"/api/generated/{g['id']}/download?format={fmt}", headers=sales).status_code == 200
