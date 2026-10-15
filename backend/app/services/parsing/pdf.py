import bisect
import re
from collections import Counter
from pathlib import Path

import pymupdf

from .base import FRONT_MATTER_TITLE, ParsedDocument, ParsedSection, ParseError


def parse_pdf(path: Path) -> ParsedDocument:
    with pymupdf.open(path) as pdf:
        pages = [page.get_text("text") for page in pdf]
        if not any(p.strip() for p in pages):
            raise ParseError("텍스트를 추출할 수 없습니다. 스캔 이미지 PDF는 아직 지원하지 않습니다.")
        title = (pdf.metadata or {}).get("title") or None
        toc = [(lvl, t.strip(), p) for lvl, t, p in pdf.get_toc(simple=True) if p >= 1 and t.strip()]
        sections = _sections_from_toc(toc, pages) if toc else _sections_from_fonts(pdf)
        return ParsedDocument(title=title, page_count=len(pages), sections=sections)


def _sections_from_toc(toc: list[tuple[int, str, int]], pages: list[str]) -> list[ParsedSection]:
    """PDF 책갈피 목차를 기준으로 섹션을 나눈다.

    같은 쪽에 여러 제목이 있을 수 있으므로 쪽 단위가 아니라
    본문에서 제목 문자열 위치를 찾아 그 지점에서 자른다.
    """
    offsets: list[int] = []
    full = ""
    for page in pages:
        offsets.append(len(full))
        full += page + "\n"

    def page_of(pos: int) -> int:
        return bisect.bisect_right(offsets, pos)  # 1부터 시작하는 쪽 번호

    starts: list[int] = []  # 섹션 경계 (제목 시작 위치)
    bodies: list[int] = []  # 본문 시작 위치 (제목 줄 다음)
    prev = 0
    for _level, title, page in toc:
        page = min(page, len(pages))
        page_begin = offsets[page - 1]
        page_end = offsets[page] if page < len(pages) else len(full)
        m = _title_pattern(title).search(full, max(page_begin, prev), page_end)
        pos = m.start() if m else max(page_begin, prev)
        starts.append(pos)
        bodies.append(m.end() if m else pos)
        prev = bodies[-1]

    sections: list[ParsedSection] = []
    front = full[: starts[0]].strip()
    if front:
        sections.append(ParsedSection(FRONT_MATTER_TITLE, 1, front, 1, page_of(starts[0] - 1)))
    for i, (level, title, _page) in enumerate(toc):
        begin = starts[i]
        end = max(bodies[i], starts[i + 1]) if i + 1 < len(starts) else len(full)
        sections.append(
            ParsedSection(
                title=title,
                level=level,
                text=full[bodies[i] : end].strip(),
                page_start=page_of(begin),
                page_end=page_of(max(begin, end - 1)),
            )
        )
    return sections


def _title_pattern(title: str) -> re.Pattern[str]:
    words = title.split()[:12]
    return re.compile(r"\s+".join(re.escape(w) for w in words), re.IGNORECASE)


def _sections_from_fonts(pdf: pymupdf.Document) -> list[ParsedSection]:
    """책갈피 목차가 없을 때 본문보다 큰 글꼴의 짧은 줄을 제목으로 추정한다."""
    lines: list[tuple[int, float, str]] = []
    sizes: Counter[float] = Counter()
    for page_no, page in enumerate(pdf, start=1):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = line["spans"]
                text = "".join(s["text"] for s in spans).strip()
                if not text:
                    continue
                size = round(max(s["size"] for s in spans), 1)
                sizes[size] += len(text)
                lines.append((page_no, size, text))

    body_size = sizes.most_common(1)[0][0]
    heading_sizes = sorted({sz for _, sz, t in lines if sz >= body_size * 1.15 and len(t) <= 120}, reverse=True)[:3]
    level_of = {sz: i + 1 for i, sz in enumerate(heading_sizes)}

    sections: list[ParsedSection] = []
    current: ParsedSection | None = None
    for page_no, size, text in lines:
        if size in level_of and len(text) <= 120:
            # 여러 줄로 나뉜 제목은 하나로 합친다.
            if current and not current.text and current.level == level_of[size] and current.page_start == page_no:
                current.title += " " + text
                continue
            current = ParsedSection(text, level_of[size], "", page_no, page_no)
            sections.append(current)
        else:
            if current is None:
                current = ParsedSection(FRONT_MATTER_TITLE, 1, "", page_no, page_no)
                sections.append(current)
            current.text += text + "\n"
            current.page_end = page_no
    for s in sections:
        s.text = s.text.strip()
    return sections
