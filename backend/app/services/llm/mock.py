import re

from .base import OverviewInput, SectionInput, SectionResult

_STEP = re.compile(r"^\s*(?:\d+[.)]|step\s*\d+)\s*(.+)", re.IGNORECASE)
_WARNING = re.compile(r"warning|caution|important|주의|경고", re.IGNORECASE)


class MockProvider:
    """API 키 없이 화면과 흐름을 개발하기 위한 가짜 요약 엔진."""

    async def summarize_section(self, item: SectionInput) -> SectionResult:
        lines = [ln.strip() for ln in item.text.splitlines() if ln.strip()]
        steps = [m.group(1) for ln in lines if (m := _STEP.match(ln))][:8]
        warnings = [ln for ln in lines if _WARNING.search(ln)][:5]
        body = "\n".join(f"- {ln}" for ln in lines[:5]) or "- (본문 없음)"
        header = f"> [모의 요약 · {item.target_language}] {item.section_path}"
        if item.feedback:
            header += f"\n> 반영한 피드백: {item.feedback}"
        return SectionResult(summary_markdown=f"{header}\n\n{body}", key_steps=steps, warnings=warnings)

    async def summarize_overview(self, item: OverviewInput) -> str:
        titles = "\n".join(f"- {title}" for title, _ in item.sections[:15])
        return f"[모의 개요] {item.vendor} · {item.document_title}\n\n주요 목차:\n{titles}"
