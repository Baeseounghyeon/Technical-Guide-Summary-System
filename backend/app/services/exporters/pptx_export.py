import re
from pathlib import Path

from pptx import Presentation
from pptx.presentation import Presentation as PptxPresentation
from pptx.util import Inches, Pt

from ..llm.base import language_native_name
from .base import REVISION_COLUMNS, ExportContext, open_template, page_label, strip_inline_markup

BULLETS_PER_SLIDE = 7
_LIST_PREFIX = re.compile(r"^\s*(?:[-*+]|#{1,6}|>)\s*")


def build_pptx(ctx: ExportContext, out_path: Path) -> None:
    if ctx.template_path:
        prs = Presentation(open_template(ctx.template_path))
    else:
        prs = Presentation()
        prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)

    # 표지
    slide = prs.slides.add_slide(prs.slide_layouts[0])
    if slide.shapes.title is not None:
        slide.shapes.title.text = ctx.title
    if len(slide.placeholders) > 1:
        slide.placeholders[1].text = (
            f"{ctx.vendor} · {language_native_name(ctx.target_language)} · v{ctx.doc_version} · {ctx.created_at:%Y-%m-%d}"
        )
    if ctx.logo_path:
        slide.shapes.add_picture(str(ctx.logo_path), prs.slide_width - Inches(2.3), Inches(0.3), height=Inches(0.8))

    if ctx.revisions:
        _add_revision_slide(prs, ctx.revisions)

    if ctx.overview:
        _add_bullet_slides(prs, "개요", _markdown_lines(ctx.overview))

    for section in ctx.sections:
        if not section.content:
            continue
        bullets = section.key_steps or _markdown_lines(section.content)
        bullets = bullets + [f"⚠ {w}" for w in section.warnings]
        label = page_label(section)
        if label:
            bullets.append(f"({label})")
        _add_bullet_slides(prs, section.title, bullets)

    prs.save(str(out_path))


def _markdown_lines(markdown: str) -> list[str]:
    lines = []
    for line in markdown.splitlines():
        if not line.strip() or line.strip().startswith("```"):
            continue
        lines.append(strip_inline_markup(_LIST_PREFIX.sub("", line).strip()))
    return lines


def _content_layout(prs: PptxPresentation):
    return prs.slide_layouts[1] if len(prs.slide_layouts) > 1 else prs.slide_layouts[0]


def _add_bullet_slides(prs: PptxPresentation, title: str, bullets: list[str]) -> None:
    chunks = [bullets[i : i + BULLETS_PER_SLIDE] for i in range(0, len(bullets), BULLETS_PER_SLIDE)] or [[]]
    for index, chunk in enumerate(chunks):
        slide = prs.slides.add_slide(_content_layout(prs))
        if slide.shapes.title is not None:
            slide.shapes.title.text = title if index == 0 else f"{title} (계속)"
        body = next((p for p in slide.placeholders if p.placeholder_format.idx == 1), None)
        if body is None:
            body = slide.shapes.add_textbox(Inches(0.7), Inches(1.6), prs.slide_width - Inches(1.4), Inches(5))
        frame = body.text_frame
        frame.clear()
        for i, text in enumerate(chunk):
            paragraph = frame.paragraphs[0] if i == 0 else frame.add_paragraph()
            paragraph.text = text
            paragraph.font.size = Pt(18)


def _add_revision_slide(prs: PptxPresentation, revisions: list[dict]) -> None:
    slide = prs.slides.add_slide(_content_layout(prs))
    if slide.shapes.title is not None:
        slide.shapes.title.text = "문서 이력"
    for placeholder in list(slide.placeholders):
        if placeholder.placeholder_format.idx == 1:
            placeholder._element.getparent().remove(placeholder._element)
    rows, cols = len(revisions) + 1, len(REVISION_COLUMNS)
    table = slide.shapes.add_table(
        rows, cols, Inches(0.5), Inches(1.6), prs.slide_width - Inches(1), Inches(0.4) * rows
    ).table
    for c, (_, label) in enumerate(REVISION_COLUMNS):
        table.cell(0, c).text = label
    for r, rev in enumerate(revisions, start=1):
        for c, (key, _) in enumerate(REVISION_COLUMNS):
            table.cell(r, c).text = str(rev.get(key) or "")
    for row in table.rows:
        for cell in row.cells:
            for paragraph in cell.text_frame.paragraphs:
                paragraph.font.size = Pt(11)
