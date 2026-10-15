"""요약 엔진(API / Claude Code 구독)이 함께 쓰는 지시문과 출력 형식."""

from .base import OverviewInput, SectionInput, language_name

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


def glossary_text(glossary: list[tuple[str, str]]) -> str | None:
    if not glossary:
        return None
    terms = "\n".join(f"{src} => {dst}" for src, dst in sorted(glossary))
    return f"Glossary:\n{terms}"


def section_prompt(item: SectionInput) -> str:
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
    return "\n".join(parts)


def overview_prompt(item: OverviewInput) -> str:
    joined = "\n\n".join(f"## {title}\n{summary}" for title, summary in item.sections)
    return (
        f"Target language: {language_name(item.target_language)}\n"
        f"Vendor: {item.vendor}\nDocument: {item.document_title}\n\n"
        "Write an executive overview of this guide for partner engineers: purpose, scope, "
        "main tasks covered and the most important cautions. 5-10 bullet points.\n\n"
        f"<section_summaries>\n{joined}\n</section_summaries>"
    )
