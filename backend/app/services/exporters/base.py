import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ExportSection:
    title: str
    level: int
    content: str | None
    key_steps: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    page_start: int | None = None
    page_end: int | None = None


@dataclass
class ExportContext:
    title: str
    vendor: str
    target_language: str
    doc_version: str
    created_at: datetime
    overview: str | None
    sections: list[ExportSection]
    logo_path: Path | None = None
    template_path: Path | None = None
    # 문서 이력 관리 표 (과거 생성분 + 이번 생성분)
    revisions: list[dict] = field(default_factory=list)


REVISION_COLUMNS = [
    ("doc_version", "버전"),
    ("date", "일자"),
    ("company", "소속 회사"),
    ("department", "부서"),
    ("engineer", "엔지니어"),
    ("phone", "연락처"),
    ("email", "메일"),
    ("change_note", "변경 내용"),
]


def page_label(section: ExportSection) -> str | None:
    if section.page_start is None:
        return None
    if section.page_end and section.page_end != section.page_start:
        return f"원본 p.{section.page_start}–{section.page_end}"
    return f"원본 p.{section.page_start}"


_INLINE_MARKUP = re.compile(r"\*\*(.+?)\*\*|`(.+?)`")


def strip_inline_markup(text: str) -> str:
    return _INLINE_MARKUP.sub(lambda m: m.group(1) or m.group(2), text)


def open_template(path: Path) -> Path | io.BytesIO:
    """.dotx/.potx 템플릿은 콘텐츠 형식만 문서용으로 바꿔서 연다 (python-docx/pptx 제약)."""
    if path.suffix.lower() not in (".dotx", ".potx"):
        return path
    buf = io.BytesIO()
    with zipfile.ZipFile(path) as zin, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "[Content_Types].xml":
                data = data.replace(
                    b"wordprocessingml.template.main+xml", b"wordprocessingml.document.main+xml"
                ).replace(b"presentationml.template.main+xml", b"presentationml.presentation.main+xml")
            zout.writestr(item, data)
    buf.seek(0)
    return buf
