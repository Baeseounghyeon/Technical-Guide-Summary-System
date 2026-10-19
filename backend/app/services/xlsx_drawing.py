"""엑셀 양식의 도형·그림(드로잉)을 그대로 옮긴다.

openpyxl 은 셀은 잘 다루지만 저장할 때 텍스트 상자 같은 도형을 버린다 (견적서의 '견 적 서 / QUOTATION' 제목 상자,
회사·대표이사 상자 등). 그래서 셀은 openpyxl 로 채우고, 저장한 파일에 양식의 드로잉 XML·그림을 다시 넣는다.
품목 행을 늘렸으면 늘린 행 아래에 있는 도형·그림도 그만큼 내린다.
"""

import io
import posixpath
import re
import zipfile

REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
DRAWING_REL = REL_NS + "/drawing"
DRAWING_CT = "application/vnd.openxmlformats-officedocument.drawing+xml"
IMAGE_CT = {"png": "image/png", "jpeg": "image/jpeg", "jpg": "image/jpeg", "gif": "image/gif", "emf": "image/x-emf", "wmf": "image/x-wmf"}


def _first_sheet(z: zipfile.ZipFile) -> str:
    wb = z.read("xl/workbook.xml").decode("utf8")
    rid = re.search(r'<sheet\b[^>]*\br:id="([^"]+)"', wb).group(1)
    rels = z.read("xl/_rels/workbook.xml.rels").decode("utf8")
    target = re.search(rf'<Relationship\b[^>]*Id="{rid}"[^>]*Target="([^"]+)"', rels) or re.search(
        rf'<Relationship\b[^>]*Target="([^"]+)"[^>]*Id="{rid}"', rels
    )
    path = target.group(1).lstrip("/")
    return path if path.startswith("xl/") else posixpath.normpath(posixpath.join("xl", path))


def _rels_path(part: str) -> str:
    d, f = posixpath.split(part)
    return f"{d}/_rels/{f}.rels"


def read_drawing(data: bytes) -> dict | None:
    """양식(xlsx)의 첫 시트 드로잉: {xml, rels, media: {경로: 바이트}}. 없으면 None."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        sheet = _first_sheet(z)
        rels_path = _rels_path(sheet)
        if rels_path not in z.namelist():
            return None
        rels = z.read(rels_path).decode("utf8")
        m = re.search(r'<Relationship\b[^>]*Type="[^"]*/drawing"[^>]*/>', rels)
        if not m:
            return None
        target = re.search(r'Target="([^"]+)"', m.group(0)).group(1)
        drawing = posixpath.normpath(posixpath.join(posixpath.dirname(sheet), target)) if not target.startswith("/") else target.lstrip("/")
        xml = z.read(drawing).decode("utf8")
        d_rels_path = _rels_path(drawing)
        d_rels = z.read(d_rels_path).decode("utf8") if d_rels_path in z.namelist() else None
        media = {}
        for t in re.findall(r'Target="([^"]+)"', d_rels or ""):
            p = posixpath.normpath(posixpath.join(posixpath.dirname(drawing), t))
            if p in z.namelist():
                media[p] = z.read(p)
        return {"xml": xml, "rels": d_rels, "media": media}


def drop_shapes(drawing: dict, names: set[str]) -> dict:
    """이름이 names 에 있는 도형·그림을 뺀다 (예: 회사 로고 '그림 6')."""
    def keep(m: re.Match) -> str:
        name = re.search(r'<xdr:cNvPr\b[^>]*\bname="([^"]*)"', m.group(0))
        return "" if name and name.group(1) in names else m.group(0)

    xml = re.sub(r"<xdr:(twoCellAnchor|oneCellAnchor|absoluteAnchor)\b.*?</xdr:\1>", keep, drawing["xml"], flags=re.S)
    # 더 이상 쓰지 않는 그림 파일과 연결도 뺀다
    used = set(re.findall(r'r:(?:embed|link|id)="([^"]+)"', xml))
    rels, media = drawing["rels"], dict(drawing["media"])
    if rels:
        for rel in re.findall(r"<Relationship\b[^>]*/>", rels):
            rid = re.search(r'Id="([^"]+)"', rel).group(1)
            if rid not in used:
                rels = rels.replace(rel, "")
                target = posixpath.basename(re.search(r'Target="([^"]+)"', rel).group(1))
                media = {k: v for k, v in media.items() if posixpath.basename(k) != target}
    return {"xml": xml, "rels": rels, "media": media}


def shift_anchors(xml: str, at: int, count: int) -> str:
    """at(1부터 센 행) 앞에 count 행을 넣었을 때 그 아래 도형·그림을 내린다."""
    if count <= 0:
        return xml
    zero = at - 1

    def move(m: re.Match) -> str:
        row = int(m.group(2))
        return f"{m.group(1)}{row + count if row >= zero else row}{m.group(3)}"

    return re.sub(r"(<xdr:(?:from|to)>.*?<xdr:row>)(\d+)(</xdr:row>)", move, xml, flags=re.S)


def put_drawing(data: bytes, drawing: dict) -> bytes:
    """openpyxl 이 저장한 파일(드로잉 없음)의 첫 시트에 양식 드로잉을 붙인다."""
    src = zipfile.ZipFile(io.BytesIO(data))
    names = src.namelist()
    sheet = _first_sheet(src)
    out = io.BytesIO()
    drawing_part = "xl/drawings/drawing1.xml"
    i = 1
    while drawing_part in names:
        i += 1
        drawing_part = f"xl/drawings/drawing{i}.xml"
    rels_path = _rels_path(sheet)
    sheet_rels = src.read(rels_path).decode("utf8") if rels_path in names else (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'
    )
    rid = "rIdQuoteDrawing"
    target = posixpath.relpath(drawing_part, posixpath.dirname(sheet))
    sheet_rels = sheet_rels.replace("</Relationships>", f'<Relationship Id="{rid}" Type="{DRAWING_REL}" Target="{target}"/></Relationships>')
    sheet_xml = src.read(sheet).decode("utf8")
    tag = f'<drawing xmlns:r="{REL_NS}" r:id="{rid}"/>'
    pos = min((sheet_xml.find(t) for t in ("<legacyDrawing", "<legacyDrawingHF", "<picture", "<oleObjects", "<controls", "<webPublishItems", "<tableParts", "<extLst", "</worksheet>") if sheet_xml.find(t) >= 0))
    sheet_xml = sheet_xml[:pos] + tag + sheet_xml[pos:]
    ct = src.read("[Content_Types].xml").decode("utf8")
    ct = ct.replace("</Types>", f'<Override PartName="/{drawing_part}" ContentType="{DRAWING_CT}"/></Types>')
    for path in drawing["media"]:
        ext = path.rsplit(".", 1)[-1].lower()
        if ext in IMAGE_CT and f'Extension="{ext}"' not in ct:
            ct = ct.replace("</Types>", f'<Default Extension="{ext}" ContentType="{IMAGE_CT[ext]}"/></Types>')
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            if n == sheet:
                z.writestr(n, sheet_xml)
            elif n == rels_path:
                continue
            elif n == "[Content_Types].xml":
                z.writestr(n, ct)
            elif n in drawing["media"]:
                continue
            else:
                z.writestr(n, src.read(n))
        z.writestr(rels_path, sheet_rels)
        z.writestr(drawing_part, drawing["xml"])
        if drawing["rels"]:
            # 그림 경로는 양식과 같은 xl/media/… 를 그대로 쓴다
            z.writestr(_rels_path(drawing_part), drawing["rels"])
        for path, blob in drawing["media"].items():
            z.writestr(path, blob)
    return out.getvalue()
