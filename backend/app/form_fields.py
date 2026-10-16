"""규격서·견적서 생성의 필수 입력 항목.

아직 항목이 정해지지 않아 테스트용 5개(항목 A~E)를 둔다. 항목이 정해지면 이 목록만 바꾸면
생성 화면, 재사용 채우기, PDF·Word 양식이 함께 바뀐다.
- key: 저장 키 / label: 화면·문서에 보이는 이름 / hint: 입력 안내 / wide: 두 칸을 다 쓰는 긴 입력
"""

FORM_FIELDS: dict[str, list[dict]] = {
    "spec": [
        {"key": "a", "label": "항목 A", "hint": "예: 제품명", "wide": False},
        {"key": "b", "label": "항목 B", "hint": "예: 모델·버전", "wide": False},
        {"key": "c", "label": "항목 C", "hint": "예: 수량", "wide": False},
        {"key": "d", "label": "항목 D", "hint": "예: 납품처", "wide": False},
        {"key": "e", "label": "항목 E", "hint": "예: 요구 사양 상세", "wide": True},
    ],
    "quote": [
        {"key": "a", "label": "항목 A", "hint": "예: 고객사", "wide": False},
        {"key": "b", "label": "항목 B", "hint": "예: 제품명", "wide": False},
        {"key": "c", "label": "항목 C", "hint": "예: 수량", "wide": False},
        {"key": "d", "label": "항목 D", "hint": "예: 단가", "wide": False},
        {"key": "e", "label": "항목 E", "hint": "예: 조건·비고", "wide": True},
    ],
}

FORM_TITLES = {"spec": "규격서", "quote": "견적서"}


def _norm(text: str) -> str:
    return "".join(text.split()).lower()


def fill_from_sections(doc_type: str, sections: list[tuple[str, str]]) -> dict[str, str]:
    """등록한 문서의 목차(제목, 본문)로 입력 항목을 채운다.

    1) 목차 제목이 항목 이름(예: '항목 A', '1. 항목 A')을 담고 있으면 그 본문을 넣는다.
    2) 남은 항목은 아직 쓰이지 않은 목차를 순서대로 넣는다(제목 + 본문).
    """
    fields = FORM_FIELDS[doc_type]
    values: dict[str, str] = {}
    used: set[int] = set()
    for f in fields:
        label = _norm(f["label"])
        for i, (title, text) in enumerate(sections):
            if i not in used and label in _norm(title):
                values[f["key"]] = text.strip() or title.strip()
                used.add(i)
                break
    rest = [(t, x) for i, (t, x) in enumerate(sections) if i not in used and (t.strip() or x.strip())]
    for f in fields:
        if f["key"] not in values and rest:
            title, text = rest.pop(0)
            values[f["key"]] = "\n".join(v for v in (title.strip(), text.strip()) if v)
    return {f["key"]: values.get(f["key"], "") for f in fields}
