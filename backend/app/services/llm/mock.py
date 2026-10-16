import math
import re
from difflib import SequenceMatcher

from .base import CompareInput, FindingResult, OverviewInput, SectionInput, SectionResult, TocEntry
from .prompts import section_result

_STEP = re.compile(r"^\s*(?:\d+[.)]|step\s*\d+)\s*(.+)", re.IGNORECASE)
_WARNING = re.compile(r"warning|caution|important|주의|경고", re.IGNORECASE)

# 언어와 무관하게 비교할 수 있는 기술 낱말: 경로·하이픈 낱말(aer-cli, zero-touch)
_TECH_WORD = re.compile(r"[A-Za-z][\w]*(?:[-_/][\w]+)+")
_VALUE = re.compile(r"\b\d+(?:\.\d+)+\b|\b\d{3,5}\b")
_COMMAND = re.compile(r"`([^`]+)`")
_WORD_BEFORE = re.compile(r"([A-Za-z가-힣]+)\W*$")
_NUMBERING = re.compile(r"^[\d.\s]+")


class MockProvider:
    """API 키 없이 화면과 흐름을 개발하기 위한 가짜 엔진. 판단력은 없고 명백한 값 차이만 찾는다."""

    async def summarize_section(self, item: SectionInput) -> SectionResult:
        lines = [ln.strip() for ln in item.text.splitlines() if ln.strip()]
        steps = [m.group(1) for ln in lines if (m := _STEP.match(ln))][:8]
        warnings = [ln for ln in lines if _WARNING.search(ln)][:5]
        others = [ln for ln in lines if not _STEP.match(ln) and not _WARNING.search(ln)][:5]
        # 실제 엔진과 같은 형식: 본문 + 번호 절차 + '> ⚠' 주의 줄 (목록은 본문에서 뽑는다)
        parts = [f"> [모의 요약 · {item.target_language}] {item.section_path}"]
        if item.feedback:
            parts.append(f"> 반영한 피드백: {item.feedback}")
        parts.append("\n".join(f"- {ln}" for ln in others) or "- (본문 없음)")
        if steps:
            parts.append("\n".join(f"{i}. {s}" for i, s in enumerate(steps, 1)))
        if warnings:
            parts.append("\n".join(f"> ⚠ {w}" for w in warnings))
        return section_result("\n\n".join(parts))

    async def summarize_overview(self, item: OverviewInput) -> str:
        titles = "\n".join(f"- {title}" for title, _ in item.sections[:15])
        return f"[모의 개요] {item.vendor} · {item.document_title}\n\n주요 목차:\n{titles}"

    async def match_sections(self, partner: list[TocEntry], vendor: list[TocEntry]) -> dict[int, int | None]:
        result: dict[int, int | None] = {}
        for p in partner:
            best_key, best_score = None, 0.0
            for v in vendor:
                score = _match_score(p, v)
                if score > best_score:
                    best_key, best_score = v.key, score
            result[p.key] = best_key if best_score >= 0.35 else None
        return result

    async def compare_section(self, item: CompareInput) -> list[FindingResult]:
        findings: list[FindingResult] = []
        seen: set[str] = set()
        for m in _VALUE.finditer(item.partner_text):
            value = m.group(0)
            if value in item.vendor_text or value in seen:
                continue
            context = _word_before(item.partner_text, m.start())
            vendor_value = _vendor_value_after(item.vendor_text, context, is_version="." in value)
            if vendor_value and vendor_value != value:
                seen.add(value)
                before = _sentence_at(item.partner_text, m.start())
                findings.append(
                    FindingResult(
                        category="wrong_value",
                        severity="high",
                        before=before,
                        after=before.replace(value, vendor_value),
                        reason=f"[모의 검토] 벤더 원본에는 {context} 값이 '{vendor_value}'(으)로 되어 있습니다.",
                        evidence=_sentence_at(item.vendor_text, item.vendor_text.index(vendor_value)),
                    )
                )
        for m in _COMMAND.finditer(item.partner_text):
            command = m.group(1)
            if command in item.vendor_text:
                continue
            head = command.split()[0]
            same_tool = [c for c in _COMMAND.findall(item.vendor_text) if c.split()[0] == head]
            if len(same_tool) == 1:
                before = _sentence_at(item.partner_text, m.start())
                findings.append(
                    FindingResult(
                        category="wrong_command",
                        severity="medium",
                        before=before,
                        after=before.replace(command, same_tool[0]),
                        reason=f"[모의 검토] 벤더 원본의 명령은 `{same_tool[0]}` 입니다.",
                        evidence=_sentence_at(item.vendor_text, item.vendor_text.index(same_tool[0])),
                    )
                )
        return findings


def _tech_tokens(text: str) -> set[str]:
    """기술 낱말 + 숫자·버전 + 숫자 앞 낱말(port, firmware 등)."""
    tokens = {t.lower() for t in _TECH_WORD.findall(text)}
    for m in _VALUE.finditer(text):
        tokens.add(m.group(0))
        if word := _word_before(text, m.start()):
            tokens.add(word)
    return tokens


def _match_score(p: TocEntry, v: TocEntry) -> float:
    title = SequenceMatcher(None, _NUMBERING.sub("", p.title).lower(), _NUMBERING.sub("", v.title).lower()).ratio()
    pt, vt = _tech_tokens(p.title + " " + p.excerpt), _tech_tokens(v.title + " " + v.excerpt)
    if not (pt and vt):
        return title
    # 코사인 유사도: 한쪽 본문이 길어도 크게 불리하지 않고, 토큰 하나만 겹치는 짧은 항목에 과하게 끌리지 않는다.
    overlap = len(pt & vt) / math.sqrt(len(pt) * len(vt))
    return max(title, 0.4 * title + 0.6 * overlap * 2)


def _word_before(text: str, pos: int) -> str:
    m = _WORD_BEFORE.search(text[max(0, pos - 30) : pos])
    return m.group(1).lower() if m else ""


def _vendor_value_after(vendor_text: str, context: str, *, is_version: bool) -> str | None:
    if not context:
        return None
    for m in _VALUE.finditer(vendor_text):
        if ("." in m.group(0)) == is_version and _word_before(vendor_text, m.start()) == context:
            return m.group(0)
    return None


def _sentence_at(text: str, pos: int) -> str:
    """pos 를 포함하는 줄(문장)을 그대로 돌려준다. 파트너 원문에 그대로 있어야 수정본에 반영할 수 있다."""
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    line = text[start : end if end != -1 else len(text)]
    return line.strip()
