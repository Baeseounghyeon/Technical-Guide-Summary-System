import pymupdf

from app.services.parsing import is_boilerplate
from app.services.parsing.base import split_markdown
from app.services.parsing.pdf import parse_pdf


def test_pdf_split_by_bookmarks(tmp_path):
    path = tmp_path / "toc.pdf"
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "Chapter 1 Intro\nIntro body text.")
    pdf.new_page().insert_text((72, 72), "Chapter 2 Setup\nSetup body.\nSection 2.1 Network\nNetwork body.")
    pdf.set_toc([[1, "Chapter 1 Intro", 1], [1, "Chapter 2 Setup", 2], [2, "Section 2.1 Network", 2]])
    pdf.save(path)

    parsed = parse_pdf(path)
    sections = {s.title: s for s in parsed.sections}
    assert parsed.page_count == 2
    # 같은 쪽에 있는 두 제목을 제목 위치에서 정확히 나눈다.
    assert "Setup body" in sections["Chapter 2 Setup"].text
    assert "Network body" not in sections["Chapter 2 Setup"].text
    assert "Network body" in sections["Section 2.1 Network"].text
    # 본문에는 제목 줄이 다시 들어가지 않는다.
    assert not sections["Chapter 2 Setup"].text.startswith("Chapter 2")
    assert sections["Section 2.1 Network"].level == 2
    assert sections["Section 2.1 Network"].page_start == 2


def test_pdf_without_bookmarks_uses_font_size(tmp_path):
    path = tmp_path / "plain.pdf"
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Installation", fontsize=20)
    page.insert_text((72, 110), "Run the installer and accept the license.", fontsize=11)
    page.insert_text((72, 150), "Upgrade", fontsize=20)
    page.insert_text((72, 190), "Back up the configuration first.", fontsize=11)
    pdf.save(path)

    titles = [s.title for s in parse_pdf(path).sections]
    assert titles == ["Installation", "Upgrade"]


def test_split_markdown_levels():
    sections = split_markdown("intro\n# A\ntext a\n## A.1\ntext a1\n# B\n")
    assert [(s.title, s.level) for s in sections] == [("(표지·서문)", 1), ("A", 1), ("A.1", 2), ("B", 1)]
    assert sections[2].text == "text a1"


def test_boilerplate_detection():
    assert is_boilerplate("Copyright Notice")
    assert is_boilerplate("목차")
    assert not is_boilerplate("Indexing configuration")
