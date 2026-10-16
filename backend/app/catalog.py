"""벤더별 제품군·상세 목록. 문서 등록과 목록 필터(벤더 → 제품군 → 상세)에 쓴다.

키는 벤더 도메인 이름(vendors.name)과 같아야 한다. 상세가 없는 제품군은 빈 목록.
새 제품이 생기면 여기에 추가한다.
"""

PRODUCT_CATALOG: dict[str, dict[str, list[str]]] = {
    "Thales": {
        "CipherTrust Manager": ["k170v", "k470v", "k570"],
        "Luna HSM": [],
        "DDC": [],
        "CCKM": [],
        "CTE": [],
        "CDP": [],
        "KMIP": [],
        "CADP": [],
        "BDT": [],
    },
    "Ahnlab": {
        "EPP": ["EDR", "EPM", "EPrM", "ESA", "EDC"],
        "EDR": [],
        "V3": ["V3 IS/ES", "V3 Net for Unix/Linux Server", "V3 Net for Window Server"],
        "XTG": [],
        "TG": [],
        "AIPS": [],
        "DPX": [],
        "TMS": [],
        "MDS": ["MDS", "MDS Manager", "MTA"],
        "XTD": [],
        "EPS": [],
        "CPP": ["Anti-Marware", "Host IPS", "Application Control", "Container Security"],
        "ASTx/ASKd": [],
        "Mobile": [],
        "TS Engine Suite": [],
    },
}


def validate_product(vendor_name: str, product: str | None, detail: str | None) -> str | None:
    """벤더에 맞지 않는 제품군·상세면 오류 메시지를, 맞으면 None 을 돌려준다. 목록에 없는 벤더는 자유 입력을 허용."""
    if not product:
        return "제품군을 고르기 전에 상세를 고를 수 없습니다." if detail else None
    families = PRODUCT_CATALOG.get(vendor_name)
    if families is None:
        return None
    if product not in families:
        return f"{vendor_name} 의 제품군이 아닙니다: {product}"
    if detail and detail not in families[product]:
        return f"{product} 의 상세 항목이 아닙니다: {detail}"
    return None
