import re
from pathlib import Path

from .base import ParsedDocument, ParsedSection, ParseError
from .office import parse_docx, parse_pptx, parse_xlsx
from .pdf import parse_pdf
from .web import parse_url

SUPPORTED_EXTENSIONS = {".pdf": "pdf", ".docx": "docx", ".pptx": "pptx", ".xlsx": "xlsx"}

# 목차 확인 단계에서 기본으로 요약 대상에서 빼 둘 항목
_BOILERPLATE = re.compile(
    r"^\s*(?:copyright.*|legal notices?|notices?|trademarks?|disclaimers?|index|table of contents|contents"
    r"|revision history|저작권.*|상표.*|법적 고지|색인|목차|개정 이력|\(표지·서문\))\s*$",
    re.IGNORECASE,
)


def parse_source(source_type: str, *, path: Path | None = None, url: str | None = None) -> ParsedDocument:
    if source_type == "url":
        assert url
        return parse_url(url)
    assert path
    parser = {"pdf": parse_pdf, "docx": parse_docx, "pptx": parse_pptx, "xlsx": parse_xlsx}.get(source_type)
    if parser is None:
        raise ParseError(f"지원하지 않는 형식입니다: {source_type}")
    return parser(path)


def is_boilerplate(title: str) -> bool:
    return bool(_BOILERPLATE.search(title))


__all__ = [
    "SUPPORTED_EXTENSIONS",
    "ParseError",
    "ParsedDocument",
    "ParsedSection",
    "is_boilerplate",
    "parse_source",
]
