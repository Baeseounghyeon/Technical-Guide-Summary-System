from ...config import settings
from .base import (
    CompareInput,
    FindingResult,
    LLMError,
    LLMProvider,
    OverviewInput,
    SectionInput,
    SectionResult,
    TocEntry,
)


def get_provider() -> LLMProvider:
    if settings.llm_provider == "claude":
        from .claude import ClaudeProvider

        return ClaudeProvider()
    if settings.llm_provider == "claude_code":
        from .claude_code import ClaudeCodeProvider

        return ClaudeCodeProvider()
    from .mock import MockProvider

    return MockProvider()


__all__ = [
    "CompareInput",
    "FindingResult",
    "LLMError",
    "LLMProvider",
    "OverviewInput",
    "SectionInput",
    "SectionResult",
    "TocEntry",
    "get_provider",
]
