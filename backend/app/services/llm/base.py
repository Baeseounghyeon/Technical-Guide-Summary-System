from dataclasses import dataclass, field
from typing import Protocol

LANGUAGE_NAMES = {
    "ko": "Korean",
    "en": "English",
    "ja": "Japanese",
    "zh": "Simplified Chinese",
    "vi": "Vietnamese",
}


LANGUAGE_NATIVE_NAMES = {
    "ko": "한국어",
    "en": "English",
    "ja": "日本語",
    "zh": "中文(简体)",
    "vi": "Tiếng Việt",
}


def language_name(code: str) -> str:
    """프롬프트용 영어 이름."""
    return LANGUAGE_NAMES.get(code, code)


def language_native_name(code: str) -> str:
    """문서 표지 등 사람에게 보여줄 이름."""
    return LANGUAGE_NATIVE_NAMES.get(code, code)


class LLMError(Exception):
    pass


@dataclass
class SectionInput:
    vendor: str
    document_title: str
    section_path: str  # 예: "3. 설치 > 3.2 사전 준비"
    text: str
    target_language: str
    glossary: list[tuple[str, str]] = field(default_factory=list)
    # 재생성 요청일 때만 채워진다.
    previous_summary: str | None = None
    feedback: str | None = None


@dataclass
class SectionResult:
    summary_markdown: str
    key_steps: list[str]
    warnings: list[str]


@dataclass
class OverviewInput:
    vendor: str
    document_title: str
    target_language: str
    sections: list[tuple[str, str]]  # (제목, 요약)


class LLMProvider(Protocol):
    async def summarize_section(self, item: SectionInput) -> SectionResult: ...

    async def summarize_overview(self, item: OverviewInput) -> str: ...
