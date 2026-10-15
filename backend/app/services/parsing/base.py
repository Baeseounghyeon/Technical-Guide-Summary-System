import re
from dataclasses import dataclass, field


class ParseError(Exception):
    """사용자에게 그대로 보여줄 수 있는 파싱 실패."""


@dataclass
class ParsedSection:
    title: str
    level: int
    text: str = ""
    page_start: int | None = None
    page_end: int | None = None


@dataclass
class ParsedDocument:
    title: str | None  # 문서 메타데이터의 제목. 없으면 None
    page_count: int | None
    sections: list[ParsedSection] = field(default_factory=list)


FRONT_MATTER_TITLE = "(표지·서문)"

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def split_markdown(markdown: str) -> list[ParsedSection]:
    """Markdown 제목(#)을 기준으로 섹션을 나눈다."""
    sections: list[ParsedSection] = []
    current: ParsedSection | None = None
    for line in markdown.splitlines():
        m = _MD_HEADING.match(line)
        if m:
            current = ParsedSection(title=m.group(2).strip(), level=len(m.group(1)))
            sections.append(current)
            continue
        if current is None:
            if not line.strip():
                continue
            current = ParsedSection(title=FRONT_MATTER_TITLE, level=1)
            sections.append(current)
        current.text += line + "\n"
    for s in sections:
        s.text = s.text.strip()
    return sections
