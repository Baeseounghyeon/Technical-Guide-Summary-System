from ...config import settings
from .base import LLMError, LLMProvider, OverviewInput, SectionInput, SectionResult


def get_provider() -> LLMProvider:
    if settings.llm_provider == "claude":
        from .claude import ClaudeProvider

        return ClaudeProvider()
    if settings.llm_provider == "claude_code":
        from .claude_code import ClaudeCodeProvider

        return ClaudeCodeProvider()
    from .mock import MockProvider

    return MockProvider()


__all__ = ["LLMError", "LLMProvider", "OverviewInput", "SectionInput", "SectionResult", "get_provider"]
