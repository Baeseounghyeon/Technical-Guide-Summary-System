"""제품 가격표·매입 금액 문서에서 표(항목)를 뽑는다. 견적서 생성 3·5단계에서 사용자가 체크하고 고친다.

- Excel: 내용이 있는 첫 시트. 첫 행이 머리글.
- Word: 행이 가장 많은 표. 첫 행이 머리글.
- PDF: 쪽마다 찾은 표를 이어 붙인다 (첫 표의 머리글과 열 수가 같은 표). 표가 없으면 글 줄을 한 열로.
"""

from datetime import date, datetime
from pathlib import Path

import pymupdf
from docx import Document
from openpyxl import load_workbook

MAX_ROWS = 1000
MAX_COLS = 30


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    return " ".join(str(value).split())


def _shape(rows: list[list[str]]) -> dict:
    """빈 행·빈 끝 열을 지우고 머리글/본문으로 나눈다."""
    rows = [[_text(c) for c in r][:MAX_COLS] for r in rows]
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        return {"columns": [], "rows": []}
    width = max(max((i + 1 for i, c in enumerate(r) if c), default=0) for r in rows)
    rows = [(r + [""] * width)[:width] for r in rows]
    header = [c or f"열 {i + 1}" for i, c in enumerate(rows[0])]
    return {"columns": header, "rows": rows[1 : MAX_ROWS + 1]}


def _xlsx(path: Path) -> dict:
    """.xlsx·.xls: 내용이 있는 첫 시트."""
    from .parsing.office import sheet_rows

    for _, rows in sheet_rows(path)[1]:
        shaped = _shape(rows)
        if shaped["rows"]:
            return shaped
    return {"columns": [], "rows": []}


def _docx(path: Path) -> dict:
    tables = Document(str(path)).tables
    if not tables:
        lines = [[p.text] for p in Document(str(path)).paragraphs if p.text.strip()]
        return _shape([["내용"], *lines])
    table = max(tables, key=lambda t: len(t.rows))
    return _shape([[cell.text for cell in row.cells] for row in table.rows])


def _pdf(path: Path) -> dict:
    with pymupdf.open(str(path)) as doc:
        found: list[tuple[int, list[list[str]]]] = []  # (쪽, 표)
        for page in doc:
            try:
                found += [(page.number, t.extract()) for t in page.find_tables().tables]
            except Exception:  # noqa: BLE001 — 표 찾기 실패는 글 줄로 대신한다
                pass
        found = [(n, t) for n, t in found if t]
        if found:
            # 가장 큰 표를 기준으로, 다음 쪽에서 이어지는 같은 열 수의 표만 붙인다 (다른 작은 표는 뺀다)
            start, first = max(found, key=lambda x: len(x[1]))
            width = len(first[0])
            header = [_text(c) for c in first[0]]
            rows = list(first)
            for n, t in found:
                if n > start and len(t[0]) == width:
                    rows += [r for r in t if [_text(c) for c in r] != header]
            return _shape(rows)
        lines = [[line] for page in doc for line in page.get_text().splitlines() if line.strip()]
    return _shape([["내용"], *lines])


def extract_items(path: Path, source_type: str) -> dict:
    """{columns: [머리글…], rows: [[칸…], …]}"""
    parser = {"xlsx": _xlsx, "xls": _xlsx, "docx": _docx, "pdf": _pdf}.get(source_type)
    if parser is None:
        return {"columns": [], "rows": []}
    return parser(path)
