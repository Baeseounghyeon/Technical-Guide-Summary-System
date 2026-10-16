import bisect
import re
from collections import Counter
from pathlib import Path

import pymupdf

from .base import FRONT_MATTER_TITLE, ParsedDocument, ParsedSection, ParseError


def parse_pdf(path: Path) -> ParsedDocument:
    with pymupdf.open(path) as pdf:
        pages = _strip_running_lines([page.get_text("text") for page in pdf])
        if not any(p.strip() for p in pages):
            raise ParseError("텍스트를 추출할 수 없습니다. 스캔 이미지 PDF는 아직 지원하지 않습니다.")
        title = (pdf.metadata or {}).get("title") or None
        toc = [(lvl, t.strip(), p) for lvl, t, p in pdf.get_toc(simple=True) if p >= 1 and t.strip()]
        sections = _sections_from_toc(toc, pages) if toc else _sections_from_fonts(pdf, pages)
        return ParsedDocument(title=title, page_count=len(pages), sections=sections)


# 페이지 위·아래 몇 줄 안에서, 여러 페이지에 똑같이(숫자만 다르게) 반복되는 줄은 머리말·꼬리말로 본다.
_EDGE_TOP, _EDGE_BOTTOM = 2, 3
_DIGITS = re.compile(r"\d+")


def _edge_key(line: str) -> str:
    return _DIGITS.sub("#", " ".join(line.split()))


def _strip_running_lines(pages: list[str]) -> list[str]:
    """쪽마다 반복되는 머리말·꼬리말(문서명, 저작권, 쪽 번호, 장 제목)을 지운다.

    요약 품질을 해치고 입력 비용만 늘리므로 요약 전에 뺀다. 본문 속 반복 문장을 지우지 않도록
    각 쪽의 위·아래 가장자리 줄만 보고, 전체 쪽의 30% 이상(최소 3쪽)에서 반복될 때만 지운다.
    """
    split = [[ln for ln in page.splitlines()] for page in pages]

    def edges(lines: list[str]) -> list[int]:
        idx = [i for i, ln in enumerate(lines) if ln.strip()]
        return sorted(set(idx[:_EDGE_TOP] + idx[-_EDGE_BOTTOM:]))

    counts: Counter[str] = Counter()
    for lines in split:
        counts.update({_edge_key(lines[i]) for i in edges(lines)})
    threshold = max(3, int(len(pages) * 0.3))
    running = {k for k, n in counts.items() if n >= threshold}
    if not running:
        return pages
    cleaned = []
    for lines in split:
        drop = {i for i in edges(lines) if _edge_key(lines[i]) in running}
        cleaned.append("\n".join(ln for i, ln in enumerate(lines) if i not in drop))
    return cleaned


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


def _sections_from_fonts(pdf: pymupdf.Document, cleaned_pages: list[str]) -> list[ParsedSection]:
    """책갈피 목차가 없을 때 본문보다 큰 글꼴의 짧은 줄을 제목으로 추정한다."""
    # 머리말·꼬리말로 지운 줄은 제목·본문 후보에서도 뺀다 (쪽별로 남은 줄 목록과 대조)
    kept = [Counter(" ".join(ln.split()) for ln in page.splitlines() if ln.strip()) for page in cleaned_pages]
    lines: list[tuple[int, float, str]] = []
    sizes: Counter[float] = Counter()
    for page_no, page in enumerate(pdf, start=1):
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = line["spans"]
                text = "".join(s["text"] for s in spans).strip()
                key = " ".join(text.split())
                if not text or kept[page_no - 1][key] <= 0:
                    continue
                kept[page_no - 1][key] -= 1
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
