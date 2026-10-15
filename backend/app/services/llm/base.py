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


@dataclass
class TocEntry:
    """목차 매칭에 쓰는 항목. key 는 호출하는 쪽이 정한 식별자."""

    key: int
    title: str
    excerpt: str


FINDING_CATEGORIES = ("wrong_value", "wrong_command", "missing_step", "wrong_order", "missing_warning", "contradiction", "outdated")
SEVERITIES = ("high", "medium", "low")


@dataclass
class CompareInput:
    vendor: str
    target_language: str  # 사유(reason)를 쓸 언어
    partner_title: str
    partner_text: str
    vendor_title: str
    vendor_text: str  # 판단 근거가 되는 벤더 원본
    summary_text: str  # 승인된 요약 (참고용)


@dataclass
class FindingResult:
    category: str
    severity: str
    before: str  # 파트너 원문에 그대로 있는 문구
    after: str
    reason: str
    evidence: str  # 벤더 원본 인용


class LLMProvider(Protocol):
    async def summarize_section(self, item: SectionInput) -> SectionResult: ...

    async def summarize_overview(self, item: OverviewInput) -> str: ...

    async def match_sections(self, partner: list[TocEntry], vendor: list[TocEntry]) -> dict[int, int | None]:
        """파트너 목차 key → 대응하는 벤더 목차 key (없으면 None)."""
        ...

    async def compare_section(self, item: CompareInput) -> list[FindingResult]: ...
