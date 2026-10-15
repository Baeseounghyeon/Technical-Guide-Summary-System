"""Claude API 요약 엔진 (API 키 과금)."""

import json

from anthropic import AsyncAnthropic

from ...config import settings
from .base import LLMError, OverviewInput, SectionInput, SectionResult
from .prompts import OVERVIEW_SCHEMA, SECTION_SCHEMA, SYSTEM_PROMPT, glossary_text, overview_prompt, section_prompt


class ClaudeProvider:
    def __init__(self) -> None:
        # 키를 지정하지 않으면 SDK가 ANTHROPIC_API_KEY 환경 변수 등에서 찾는다.
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else AsyncAnthropic()

    async def summarize_section(self, item: SectionInput) -> SectionResult:
        data = await self._json_call(section_prompt(item), SECTION_SCHEMA, item.glossary, max_tokens=32000)
        return SectionResult(
            summary_markdown=data["summary_markdown"],
            key_steps=data["key_steps"],
            warnings=data["warnings"],
        )

    async def summarize_overview(self, item: OverviewInput) -> str:
        data = await self._json_call(overview_prompt(item), OVERVIEW_SCHEMA, [], max_tokens=16000)
        return data["overview_markdown"]

    async def _json_call(
        self, user_content: str, schema: dict, glossary: list[tuple[str, str]], *, max_tokens: int
    ) -> dict:
        system: list[dict] = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
        if terms := glossary_text(glossary):
            system.append({"type": "text", "text": terms, "cache_control": {"type": "ephemeral"}})

        # 긴 입력이므로 스트리밍으로 호출하고, 안전 분류기 거절 시 서버 측 대체 모델로 자동 재시도한다.
        async with self._client.beta.messages.stream(
            model=settings.claude_model,
            max_tokens=max_tokens,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=system,
            output_config={
                "effort": settings.claude_effort,
                "format": {"type": "json_schema", "schema": schema},
            },
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            message = await stream.get_final_message()

        if message.stop_reason == "refusal":
            raise LLMError("모델이 이 섹션의 요약을 거절했습니다.")
        if message.stop_reason == "max_tokens":
            raise LLMError("요약이 최대 길이를 넘었습니다. 섹션을 나눠 다시 시도하세요.")
        text = next((b.text for b in message.content if b.type == "text"), None)
        if text is None:
            raise LLMError("모델 응답에 본문이 없습니다.")
        return json.loads(text)
