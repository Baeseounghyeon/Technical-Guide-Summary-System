"""규격서·견적서 생성: 등록한 규격서를 재사용해 필수 입력값을 채우고, 고쳐서 새로 만들고, 버전 이력이 쌓인다.
업무 구분: 규격서·견적서 생성은 영업만(관리자 포함), 엔지니어는 불가."""

import io
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

    # 견적서는 단계별 견적서 생성(/api/quote-builder)으로만 만든다
    assert client.post("/api/generated", json={**body, "doc_type": "quote", "title": "견적서"}, headers=sales).status_code == 400


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


def _sales(client, admin, email: str, partner_id: int) -> dict:
    headers = _signup_and_approve(client, admin, email, partner_id)
    user_id = client.get("/api/auth/me", headers=headers).json()["id"]
    client.post(f"/api/admin/users/{user_id}/approve", json={"partner_id": partner_id, "track": "sales"}, headers=admin)
    return headers


def test_price_list_purchase_types_and_spec_attachments(client, tmp_path: Path):
    """제품 가격표·매입 금액: 문서 등록의 종류(영업만, PDF·Word·Excel). 규격서는 Excel 도 받고, 규격서 생성 때 둘을 첨부한다."""
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "가격표파트너", "PriceVendor")
    sales = _sales(client, admin, "price-sales@p.example.com", partner["id"])
    engineer = _signup_and_approve(client, admin, "price-eng@p.example.com", partner["id"])
    assert {"price_list", "purchase"} <= set(client.get("/api/auth/me", headers=sales).json()["permissions"])
    assert not {"price_list", "purchase"} & set(client.get("/api/auth/me", headers=engineer).json()["permissions"])

    def upload(headers, name: str, data: dict):
        with (tmp_path / name).open("rb") as f:
            return client.post("/api/documents", data={"vendor_id": vendor["id"], **data}, files={"file": (name, f)}, headers=headers)

    _xlsx(tmp_path / "spec.xlsx", [("항목 A", "Luna HSM"), ("항목 B", "A790"), ("항목 C", "2대"), ("항목 D", "본사"), ("항목 E", "FIPS 140-3")])
    spec = upload(sales, "spec.xlsx", {"doc_type": "spec", "title": "엑셀 규격서"}).json()
    assert spec["source_type"] == "xlsx"
    assert upload(sales, "spec.xlsx", {"doc_type": "brochure"}).status_code == 400  # Excel 은 규격서·가격표·매입만

    _xlsx(tmp_path / "price.xlsx", [("제품", "단가"), ("Luna HSM", 30000000)])
    assert upload(engineer, "price.xlsx", {"doc_type": "price_list"}).status_code == 403
    price = upload(sales, "price.xlsx", {"doc_type": "price_list", "title": "가격표"}).json()
    purchase = upload(sales, "price.xlsx", {"doc_type": "purchase", "title": "매입가"}).json()
    assert client.post(
        "/api/documents", data={"vendor_id": vendor["id"], "doc_type": "purchase", "url": "https://example.com"}, headers=sales
    ).status_code == 400  # 파일만
    run_pending_jobs()

    filled = client.get(f"/api/forms/spec/prefill?document_id={spec['id']}", headers=sales).json()
    assert filled["fields"] == {"a": "Luna HSM", "b": "A790", "c": "2대", "d": "본사", "e": "FIPS 140-3"}
    assert [d["title"] for d in client.get("/api/documents?doc_type=price_list", headers=sales).json()] == ["가격표"]

    body = {"doc_type": "spec", "title": "첨부 규격서", "fields": filled["fields"], "source_document_id": spec["id"]}
    assert client.post("/api/generated", json={**body, "attachments": {"price_list": purchase["id"]}}, headers=sales).status_code == 400
    g = client.post("/api/generated", json={**body, "attachments": {"price_list": price["id"], "purchase": purchase["id"]}}, headers=sales).json()
    assert [(a["label"], a["title"]) for a in g["attachments"]] == [("제품 가격표", "가격표"), ("매입 금액", "매입가")]


def _template_docx(path: Path) -> None:
    d = Document()
    d.add_paragraph("견적서: {{제목}}")
    d.add_paragraph("작성자 {{작성자}} / {{소속}} / {{전화번호}}")
    d.add_paragraph("{{제품가격표}}")
    d.add_paragraph("매입 내역")
    d.add_paragraph("{{매입금액}}")
    d.save(str(path))


def test_quote_builder_steps(client, tmp_path: Path):
    """견적서 생성: 양식 등록·변경 → 가격표·매입 금액 항목 뽑기 → 미리보기 → 생성 → 형식별 받기 → 고쳐서 다음 버전."""
    admin = login(client, *ADMIN)
    partner, vendor = _partner_with_vendor(client, admin, "견적생성파트너", "QuoteBuildVendor")
    sales = _sales(client, admin, "qb-sales@q.example.com", partner["id"])
    engineer = _signup_and_approve(client, admin, "qb-eng@q.example.com", partner["id"])

    # 1. 견적서 양식 등록 (Word·Excel 만)
    _template_docx(tmp_path / "tpl.docx")
    with (tmp_path / "tpl.docx").open("rb") as f:
        r = client.post("/api/quote-templates", data={"name": "기본 견적 양식"}, files={"file": ("tpl.docx", f)}, headers=sales)
    assert r.status_code == 201, r.text
    tpl = r.json()
    assert tpl["file_ext"] == "docx"
    with (tmp_path / "tpl.docx").open("rb") as f:
        assert client.post("/api/quote-templates", data={"name": "x"}, files={"file": ("tpl.pdf", f)}, headers=sales).status_code == 400
    with (tmp_path / "tpl.docx").open("rb") as f:
        assert client.post("/api/quote-templates", data={"name": "x"}, files={"file": ("tpl.docx", f)}, headers=engineer).status_code == 403
    assert client.put(f"/api/quote-templates/{tpl['id']}", data={"name": "견적 양식 v2"}, headers=sales).json()["name"] == "견적 양식 v2"
    assert [t["name"] for t in client.get("/api/quote-templates", headers=sales).json()] == ["견적 양식 v2"]

    # 2·4. 가격표(Excel)·매입 금액(Word 표) 등록, 3·5. 항목 뽑기
    _xlsx(tmp_path / "price.xlsx", [("제품", "모델", "단가"), ("Luna HSM", "A790", 30000000), ("CTM", "k570", 12000000.0)])
    d = Document()
    t = d.add_table(rows=3, cols=2)
    for row, values in zip(t.rows, [("품목", "매입가"), ("Luna HSM", "21,000,000"), ("CTM", "8,000,000")]):
        for cell, v in zip(row.cells, values):
            cell.text = v
    d.save(str(tmp_path / "purchase.docx"))
    with (tmp_path / "price.xlsx").open("rb") as f:
        price = client.post(
            "/api/documents", data={"vendor_id": vendor["id"], "doc_type": "price_list", "title": "가격표"},
            files={"file": ("price.xlsx", f)}, headers=sales,
        ).json()
    with (tmp_path / "purchase.docx").open("rb") as f:
        purchase = client.post(
            "/api/documents", data={"vendor_id": vendor["id"], "doc_type": "purchase", "title": "매입"},
            files={"file": ("purchase.docx", f)}, headers=sales,
        ).json()
    run_pending_jobs()
    items = client.get(f"/api/documents/{price['id']}/items", headers=sales).json()
    assert items == {"columns": ["제품", "모델", "단가"], "rows": [["Luna HSM", "A790", "30000000"], ["CTM", "k570", "12000000"]]}
    p_items = client.get(f"/api/documents/{purchase['id']}/items", headers=sales).json()
    assert p_items["columns"] == ["품목", "매입가"] and len(p_items["rows"]) == 2

    # 6·7. 작성자 + 미리보기 (양식을 채운 결과)
    body = {
        "title": "HSM 견적",
        "template_id": tpl["id"],
        "price_list_id": price["id"],
        "price": {"columns": items["columns"], "rows": [["Luna HSM", "A790", "29,000,000"]]},  # 체크·수정한 항목
        "purchase_id": purchase["id"],
        "purchase": p_items,
        "author": {"name": "영업 담당", "company": "견적생성파트너", "phone": "010-0000-0000"},
    }
    preview = client.post("/api/quote-builder/preview", json=body, headers=sales).json()
    assert "HSM 견적" in preview["html"] and "29,000,000" in preview["html"] and "영업 담당" in preview["html"]
    assert "{{" not in preview["html"] and preview["formats"] == ["docx", "pdf"]
    assert client.post("/api/quote-builder", json={**body, "price": {"columns": [], "rows": []}}, headers=sales).status_code == 400
    assert client.post("/api/quote-builder", json=body, headers=engineer).status_code == 403

    # 생성 → 형식별 받기
    q = client.post("/api/quote-builder", json=body, headers=sales)
    assert q.status_code == 201, q.text
    q = q.json()
    assert q["doc_type"] == "quote" and q["version"] == 1 and q["formats"] == ["docx", "pdf"]
    docx = client.get(f"/api/generated/{q['id']}/download?format=docx", headers=sales)
    assert docx.status_code == 200 and docx.content.startswith(b"PK")
    text = "\n".join(p.text for p in Document(io.BytesIO(docx.content)).paragraphs)
    assert "견적서: HSM 견적" in text and "영업 담당" in text
    assert client.get(f"/api/generated/{q['id']}/download?format=pdf", headers=sales).content.startswith(b"%PDF")
    assert client.get(f"/api/generated/{q['id']}/download?format=xlsx", headers=sales).status_code == 400

    # 9. 고쳐서 다시 생성 → 다음 버전
    v2 = client.post("/api/quote-builder", json={**body, "title": "HSM 견적 (수정)", "based_on_id": q["id"]}, headers=sales).json()
    assert v2["version"] == 2 and v2["root_id"] == q["id"]
    assert [g["version"] for g in client.get("/api/generated?doc_type=quote", headers=sales).json()] == [2, 1]

    # 양식 없이 만들면 기본 양식으로 PDF·Word·Excel
    v3 = client.post("/api/quote-builder", json={**body, "template_id": None}, headers=sales).json()
    assert v3["formats"] == ["pdf", "docx", "xlsx"]
    assert client.get(f"/api/generated/{v3['id']}/download?format=xlsx", headers=sales).content.startswith(b"PK")
