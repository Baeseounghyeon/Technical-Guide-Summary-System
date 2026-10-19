"""Thales 문서(PDF)에서 견적서에 쓰는 값을 뽑는다. 영업이 받는 가격표·매입 견적은 모두 이 형식이다.

- 제품 가격표 (Thales CSP Price List): 한 줄에 'SKU | 제품명 | 설명 | $ Korea Price'.
  → 제품 번호, 제품명, 설명, 리스트 가격(USD). 견적서 수식에는 쓰지 않고 품명·설명 참고용 (견적서_매핑정리.md 0·5절).
- 매입 견적 (Thales 가 유니포인트에 보낸 Signed Quote PDF): 머리(견적 번호·최종 고객·파트너·Quote Total)와
  'Quoted Products and Services' 표의 라인. 견적서 한 행 = 매입 견적 PDF 한 건 (매핑정리 1·2절).
"""

import re
from pathlib import Path

import pymupdf

PRICE_COLUMNS = ["제품 번호", "제품명", "설명", "리스트 가격(USD)"]
PURCHASE_COLUMNS = [
    "라인", "유지보수 제품 번호", "서비스", "대상 제품 번호", "대상 제품", "시리얼 번호", "계약 번호",
    "시작일", "종료일", "커버리지", "수량", "단가(USD)", "합계(USD)",
]

_PART = re.compile(r"^\d{3}-\d{6}-\d{3}-\d{3}$")
_PART_IN = re.compile(r"\d{3}-\d{6}-\d{3}-\d{3}")
_SERIAL = re.compile(r"\b[A-Z]{2}\d{6}\b")
_CONTRACT = re.compile(r"\b[A-Z]{3,5}\d-\d{5,7}\b")
_MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], start=1)}


def money(text: str) -> str:
    """'USD 14,675.68' · '$ 55,176' → '14675.68' · '55176'. 없으면 ''."""
    t = (text or "").replace("USD", "").replace("$", "").replace(",", "").strip()
    if t in ("", "-"):
        return ""
    return t[:-3] if t.endswith(".00") else t


# ---------- 제품 가격표 ----------


def parse_price_list(path: Path) -> list[list[str]]:
    """같은 높이에 놓인 글을 한 행으로 묶는다: 제품 번호(맨 왼쪽) → 제품명 → 설명 → '$ 가격' 또는 '21.0%'."""
    rows: list[list[str]] = []
    with pymupdf.open(str(path)) as doc:
        for page in doc:
            lines = []
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    text = "".join(s["text"] for s in line["spans"]).strip()
                    if text:
                        lines.append((line["bbox"][1], line["bbox"][0], text))
            for y, x, text in lines:
                if not _PART.match(text):
                    continue
                same = sorted((lx, t) for ly, lx, t in lines if abs(ly - y) <= 3 and lx > x)
                price = next((t for _, t in same if t.startswith("$") or t.endswith("%")), "")
                cells = [t for _, t in same if t != price]
                name, desc = (cells[0], " ".join(cells[1:])) if len(cells) > 1 else ("", cells[0] if cells else "")
                if not name and desc:
                    name = desc.split(",")[0].split("(")[0].strip()
                rows.append([text, name, desc or name, price if price.endswith("%") else money(price)])
    return rows


# ---------- 매입 견적 ----------


def _after(text: str, label: str) -> str:
    """'label' 다음에 나오는 첫 글 줄."""
    i = text.find(label)
    if i < 0:
        return ""
    for line in text[i + len(label):].splitlines():
        if line.strip() and not line.strip().endswith(":"):
            return line.strip()
    return ""


def _date(d: str, m: str, y: str) -> str:
    return f"{y}.{_MONTHS.get(m.lower(), 0):02d}.{int(d):02d}"


def _split_part(text: str) -> tuple[str, str]:
    """'020-160001-002-000/HSM, ENHANCED …' → ('020-160001-002-000', 'HSM, ENHANCED …')"""
    m = _PART_IN.search(text or "")
    if not m:
        return "", (text or "").strip()
    return m.group(0), text[m.end():].lstrip(" /").strip()


def _col(columns: list[str], *keys: str, exclude: tuple[str, ...] = ()) -> int | None:
    for i, c in enumerate(columns):
        low = " ".join((c or "").split()).lower()
        if all(k in low for k in keys) and not any(e in low for e in exclude):
            return i
    return None


def parse_purchase_quote(path: Path) -> dict:
    """{meta: {quote_number, date_quoted, end_user, partner, quote_total}, columns, rows}"""
    with pymupdf.open(str(path)) as doc:
        text = "\n".join(page.get_text() for page in doc)
        tables = []
        for page in doc:
            try:
                tables += [t.extract() for t in page.find_tables().tables]
            except Exception:  # noqa: BLE001
                pass
    meta = {
        "quote_number": (re.search(r"Quote Number:\s*(\S+)", text) or [None, ""])[1],
        "date_quoted": _after(text, "Date Quoted:"),
        "end_user": _after(text, "EndUser Contact:") or _after(text, "End User Account Name:"),
        "partner": _after(text, "Primary Partner Information"),
        "quote_total": money((re.search(r"Quote Total:\s*(USD\s*[\d,.]+)", text) or [None, ""])[1]),
    }
    rows: list[list[str]] = []
    for table in tables:
        if not table or not table[0]:
            continue
        head = [" ".join((c or "").split()) for c in table[0]]
        maint = _col(head, "maintenance part")
        covered = _col(head, "covered")
        if maint is None and covered is None:
            continue
        line_no = _col(head, "line")
        serial = _col(head, "serial")
        coverage = _col(head, "coverage")
        qty = _col(head, "quantity")
        unit = _col(head, "unit price", "discount", exclude=("%",)) or _col(head, "unit price")
        total = _col(head, "net line total")
        contract_col = _col(head, "contract")
        for r in table[1:]:
            get = lambda i: " ".join((r[i] or "").split()) if i is not None and i < len(r) else ""  # noqa: E731
            m_part, m_desc = _split_part(get(maint))
            c_part, c_desc = _split_part(get(covered))
            if not (m_part or c_part):
                continue
            ref = f"{get(serial)} {get(contract_col)}"
            cov = get(coverage)
            dates = re.findall(r"(\d{1,2})-([A-Za-z]+)-(\d{4})", cov)
            months = re.search(r"(\d+)\s*months?", cov, re.IGNORECASE)
            q = get(qty).replace(",", "")
            rows.append([
                get(line_no),
                m_part,
                m_desc,
                c_part,
                c_desc,
                " / ".join(dict.fromkeys(_SERIAL.findall(ref))),
                " / ".join(dict.fromkeys(_CONTRACT.findall(ref))),
                _date(*dates[0]) if len(dates) > 0 else "",
                _date(*dates[1]) if len(dates) > 1 else "",
                f"{months.group(1)} months" if months else "",
                q[:-3] if q.endswith(".00") else q,
                money(get(unit)),
                money(get(total)),
            ])
    return {"meta": meta, "columns": PURCHASE_COLUMNS, "rows": rows}
