import json

from anthropic import AsyncAnthropic

from ...config import settings
from .base import LLMError, OverviewInput, SectionInput, SectionResult, language_name

# 모든 요청에서 동일하게 유지되는 앞부분 (프롬프트 캐싱 대상). 날짜나 ID 같은 가변 값을 넣지 말 것.
SYSTEM_PROMPT = """\
You condense vendor technical guides into concise, accurate guides for partner field engineers.

Rules:
- Write in the target language named in the request, whatever the source language is.
- Keep commands, CLI syntax, code, configuration keys and values, file paths, ports, version numbers \
and product or feature names exactly as in the source. Do not translate them. For UI labels, keep the \
original label and add a translation in parentheses when it helps.
- Keep every warning, caution and important note, with its meaning intact.
- Write procedures as ordered steps, with prerequisites first.
- Use only information in the source text. Do not add facts, defaults or recommendations it does not contain.
- Aim for roughly 10-25% of the source length while keeping everything an engineer needs to do the task.
- If the section is only legal, marketing or navigation text, say so in one sentence.
- Use the glossary for consistent terminology when one is given.
"""

SECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "summary_markdown": {
            "type": "string",
            "description": "Section summary in Markdown (lists, `code`, **bold**). No top-level heading.",
        },
        "key_steps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Ordered key procedure steps, empty if the section has no procedure.",
        },
        "warnings": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Warnings and cautions from the source, translated.",
        },
    },
    "required": ["summary_markdown", "key_steps", "warnings"],
    "additionalProperties": False,
}

OVERVIEW_SCHEMA = {
    "type": "object",
    "properties": {"overview_markdown": {"type": "string"}},
    "required": ["overview_markdown"],
    "additionalProperties": False,
}


class ClaudeProvider:
    def __init__(self) -> None:
        # 키를 지정하지 않으면 SDK가 ANTHROPIC_API_KEY 환경 변수 등에서 찾는다.
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else AsyncAnthropic()

    async def summarize_section(self, item: SectionInput) -> SectionResult:
        parts = [
            f"Target language: {language_name(item.target_language)}",
            f"Vendor: {item.vendor}",
            f"Document: {item.document_title}",
            f"Section: {item.section_path}",
            "",
            "<source>",
            item.text,
            "</source>",
        ]
        if item.previous_summary is not None:
            parts += [
                "",
                "The reviewer asked for a revised summary.",
                "<previous_summary>",
                item.previous_summary,
                "</previous_summary>",
                "<reviewer_feedback>",
                item.feedback or "",
                "</reviewer_feedback>",
            ]
        data = await self._json_call("\n".join(parts), SECTION_SCHEMA, item.glossary, max_tokens=32000)
        return SectionResult(
            summary_markdown=data["summary_markdown"],
            key_steps=data["key_steps"],
            warnings=data["warnings"],
        )

    async def summarize_overview(self, item: OverviewInput) -> str:
        joined = "\n\n".join(f"## {title}\n{summary}" for title, summary in item.sections)
        prompt = (
            f"Target language: {language_name(item.target_language)}\n"
            f"Vendor: {item.vendor}\nDocument: {item.document_title}\n\n"
            "Write an executive overview of this guide for partner engineers: purpose, scope, "
            "main tasks covered and the most important cautions. 5-10 bullet points.\n\n"
            f"<section_summaries>\n{joined}\n</section_summaries>"
        )
        data = await self._json_call(prompt, OVERVIEW_SCHEMA, [], max_tokens=16000)
        return data["overview_markdown"]

    async def _json_call(
        self, user_content: str, schema: dict, glossary: list[tuple[str, str]], *, max_tokens: int
    ) -> dict:
        system: list[dict] = [{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}]
        if glossary:
            terms = "\n".join(f"{src} => {dst}" for src, dst in sorted(glossary))
            system.append({"type": "text", "text": f"Glossary:\n{terms}", "cache_control": {"type": "ephemeral"}})

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
