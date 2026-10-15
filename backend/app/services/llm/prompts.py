"""요약 엔진(API / Claude Code 구독)이 함께 쓰는 지시문과 출력 형식."""

from .base import FINDING_CATEGORIES, SEVERITIES, CompareInput, OverviewInput, SectionInput, TocEntry, language_name

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


# ---------- 2단계: 파트너 가이드 검토 ----------

REVIEW_SYSTEM_PROMPT = """\
You review technical guides written by vendor partners against the vendor's original documentation.
The vendor original is the source of truth.

Report only errors that would make an engineer do something wrong or fail:
- wrong values: ports, versions, limits, sizes, paths, defaults
- wrong or outdated commands, syntax, parameters or UI paths
- missing mandatory steps or prerequisites, or steps in the wrong order
- missing or contradicted warnings and cautions
- statements that contradict the vendor original

Do not report wording, style, formatting, translation choices, or details the partner left out \
unless the omission makes the procedure unsafe or fail. If the vendor original does not cover a \
statement, do not report it. When unsure, do not report.
"""

MATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "matches": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "partner_key": {"type": "integer"},
                    "vendor_key": {"type": "integer", "description": "-1 if no vendor section covers it"},
                },
                "required": ["partner_key", "vendor_key"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["matches"],
    "additionalProperties": False,
}

COMPARE_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "enum": list(FINDING_CATEGORIES)},
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
                    "before": {
                        "type": "string",
                        "description": "Exact verbatim substring of the partner text to replace. Shortest unique span.",
                    },
                    "after": {
                        "type": "string",
                        "description": "Corrected replacement for `before`, in the partner text's language and style.",
                    },
                    "reason": {"type": "string", "description": "Why it is wrong, in the requested language."},
                    "evidence": {"type": "string", "description": "Exact quote from the vendor original."},
                },
                "required": ["category", "severity", "before", "after", "reason", "evidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["findings"],
    "additionalProperties": False,
}


def match_prompt(partner: list[TocEntry], vendor: list[TocEntry]) -> str:
    def lines(prefix: str, entries: list[TocEntry]) -> str:
        return "\n".join(f"{prefix}{e.key}: {e.title} | {e.excerpt}" for e in entries)

    return (
        "Match each partner guide section to the vendor original section that covers the same topic. "
        "The two may be in different languages. Use titles and excerpts. "
        "Return one entry per partner section; use vendor_key -1 when nothing matches.\n\n"
        f"<vendor_sections>\n{lines('V', vendor)}\n</vendor_sections>\n\n"
        f"<partner_sections>\n{lines('P', partner)}\n</partner_sections>"
    )


def parse_matches(data: dict, partner: list[TocEntry], vendor: list[TocEntry]) -> dict[int, int | None]:
    """모델이 돌려준 매칭에서 존재하지 않는 key 는 버리고, 빠진 항목은 '대응 없음'으로 채운다."""
    vendor_keys = {v.key for v in vendor}
    result: dict[int, int | None] = {p.key: None for p in partner}
    for m in data.get("matches", []):
        if m["partner_key"] in result and m["vendor_key"] in vendor_keys:
            result[m["partner_key"]] = m["vendor_key"]
    return result


def compare_prompt(item: CompareInput) -> str:
    return "\n".join(
        [
            f"Write `reason` in {language_name(item.target_language)}.",
            f"Vendor: {item.vendor}",
            "",
            f'<vendor_original title="{item.vendor_title}">',
            item.vendor_text,
            "</vendor_original>",
            "",
            "<approved_summary>",
            item.summary_text,
            "</approved_summary>",
            "",
            f'<partner_section title="{item.partner_title}">',
            item.partner_text,
            "</partner_section>",
            "",
            "List the errors in the partner section. Return an empty list if there are none.",
        ]
    )


def overview_prompt(item: OverviewInput) -> str:
    joined = "\n\n".join(f"## {title}\n{summary}" for title, summary in item.sections)
    return (
        f"Target language: {language_name(item.target_language)}\n"
        f"Vendor: {item.vendor}\nDocument: {item.document_title}\n\n"
        "Write an executive overview of this guide for partner engineers: purpose, scope, "
        "main tasks covered and the most important cautions. 5-10 bullet points.\n\n"
        f"<section_summaries>\n{joined}\n</section_summaries>"
    )
