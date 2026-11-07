import io

from utils.extract import extract_text_from_file, omml_to_latex
from utils.structure import parse


def make_pdf(path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    st = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=st["Normal"], fontName="Helvetica-Bold", fontSize=20, spaceAfter=10)
    h2 = ParagraphStyle("h2", parent=st["Normal"], fontName="Helvetica-Bold", fontSize=15, spaceBefore=10, spaceAfter=6)
    body = ParagraphStyle("b", parent=st["Normal"], fontName="Helvetica", fontSize=11, leading=15, spaceAfter=6)
    table = Table([["Quantity", "Symbol", "Unit"], ["Force", "F", "newton"], ["Mass", "m", "kilogram"]])
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black)]))
    SimpleDocTemplate(path, pagesize=A4).build([
        Paragraph("Physics Notes", h1), Paragraph("Motion", h2),
        Paragraph("Speed is defined as the distance travelled per unit time.", body),
        Paragraph("v<super>2</super> = u<super>2</super> + 2as", body),
        Paragraph("E = mc<super>2</super> and x<sub>1</sub> + x<sub>2</sub> = s", body),
        Paragraph("Work and Energy", h2), Paragraph("Kinetic energy is the energy of a body due to its motion.", body),
        Spacer(1, 8), table,
    ])


def test_pdf_keeps_headings_tables_and_scripts(tmp_path):
    path = str(tmp_path / "n.pdf")
    make_pdf(path)
    text = extract_text_from_file(path)
    assert "# Physics Notes" in text and "## Motion" in text
    assert "v^{2} = u^{2} + 2as" in text and "x_{1} + x_{2}" in text
    assert "| Force | F | newton |" in text
    doc = parse(text)
    assert doc.tables and doc.tables[0].header == ["Quantity", "Symbol", "Unit"]
    assert any(f.raw.startswith("v^{2}") for f in doc.formulas)


def make_docx(path):
    from docx import Document
    from lxml import etree

    d = Document()
    d.add_heading("Maths", 1)
    d.add_paragraph("Quadratic formula:")
    ns = "http://schemas.openxmlformats.org/officeDocument/2006/math"
    xml = (f'<m:oMathPara xmlns:m="{ns}"><m:oMath><m:r><m:t>x=</m:t></m:r><m:f><m:num><m:r><m:t>-b±</m:t></m:r><m:rad><m:radPr>'
           f'<m:degHide m:val="1"/></m:radPr><m:deg/><m:e><m:sSup><m:e><m:r><m:t>b</m:t></m:r></m:e><m:sup><m:r><m:t>2</m:t></m:r></m:sup>'
           f'</m:sSup><m:r><m:t>-4ac</m:t></m:r></m:e></m:rad></m:num><m:den><m:r><m:t>2a</m:t></m:r></m:den></m:f></m:oMath></m:oMathPara>')
    p = d.add_paragraph()
    p._p.append(etree.fromstring(xml))
    t = d.add_table(rows=3, cols=2)
    for r, (a, b) in enumerate([("Name", "Value"), ("pi", "3.14"), ("e", "2.72")]):
        t.cell(r, 0).text, t.cell(r, 1).text = a, b
    d.add_paragraph("Item one", style="List Bullet")
    d.save(path)


def test_docx_word_equations_tables_and_headings(tmp_path):
    path = str(tmp_path / "n.docx")
    make_docx(path)
    text = extract_text_from_file(path)
    assert "# Maths" in text and "- Item one" in text and "| pi | 3.14 |" in text
    assert "\\frac{-b \\pm \\sqrt{{b}^{2}-4ac}}{2a}" in text
    doc = parse(text)
    assert doc.formulas and doc.tables


def test_pptx_input(tmp_path):
    from pptx import Presentation

    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Cells"
    s.placeholders[1].text = "The nucleus controls the cell."
    path = str(tmp_path / "n.pptx")
    prs.save(path)
    text = extract_text_from_file(path)
    assert "## Cells" in text and "nucleus" in text


def test_txt_with_odd_encoding(tmp_path):
    path = tmp_path / "n.txt"
    path.write_bytes("Café définition: énergie = mc²".encode("cp1252", errors="ignore"))
    assert "mc" in extract_text_from_file(str(path))


def test_clean_text_keeps_headings_and_drops_page_noise():
    from utils.extract import clean_text

    out = clean_text("Chapter 3 Waves\n\nPage 3\ndevel-\nopment of the cell\n12\nCopyright 2020 Someone\nNext sentence.")
    assert "Chapter 3 Waves" in out and "development" in out
    assert "Copyright" not in out and "Page 3" not in out
