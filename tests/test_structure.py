from conftest import MATHS, SAMPLE
from utils.structure import key_points, parse


def test_headings_and_title():
    doc = parse(SAMPLE)
    assert doc.title == "Physics Notes"
    titles = [s.title for s in doc.all_sections()]
    assert "Motion in a Straight Line" in titles and "Equations of motion" in titles


def test_definitions_found_in_several_phrasings():
    terms = {d.term for d in parse(SAMPLE).definitions}
    assert {"Speed", "Acceleration", "Kinetic energy"} <= terms
    assert "Quadratic equation" in {d.term for d in parse(MATHS).definitions}


def test_formulas_names_and_symbol_legend():
    doc = parse(SAMPLE)
    by_raw = {f.raw: f for f in doc.formulas}
    assert by_raw["F = ma"].name == "Newton's second law"
    assert by_raw["KE = 1/2 m v^2"].name == "Kinetic energy"
    legend = dict(by_raw["v = u + at"].used_variables)
    assert legend["v"] == "final velocity" and legend["t"] == "time"
    # the legend only lists symbols that appear in each formula
    assert "s" not in dict(by_raw["v = u + at"].used_variables)


def test_tables_from_spaces_and_pipes():
    doc = parse(SAMPLE)
    assert len(doc.tables) == 2
    assert doc.tables[0].header == ["Quantity", "Symbol", "SI Unit"]
    assert doc.tables[1].body[0] == ["Joule", "Energy", "F × d"]
    assert parse(MATHS).tables[0].body[1] == ["Rice", "90", "Medium"]


def test_latex_blocks_and_math_notes():
    doc = parse(MATHS)
    raws = [f.raw for f in doc.formulas]
    assert any("\\int_0^1" in r for r in raws)
    assert "ax^2 + bx + c = 0" in raws


def test_key_points_skip_what_other_boxes_already_show():
    pts = " ".join(sum(key_points(parse(SAMPLE)).values(), []))
    assert "Work done W = F" not in pts  # already a formula
    assert "rate of change of velocity" not in pts  # already a definition


def test_plain_notes_without_markup_still_work():
    doc = parse("Photosynthesis is the process by which plants make food. It needs sunlight and water. Chlorophyll absorbs light energy.")
    assert doc.sections and doc.word_count > 10


def test_sections_with_the_same_title_keep_their_own_content():
    text = "\n\n".join(f"# Part {i}\n\n## Basics\n\nTerm{i} is defined as the idea number {i} in these notes.\nx{i} = {i}y + 1\n\n| a | b |\n|---|---|\n| {i} | {i * 2} |" for i in range(1, 4))
    doc = parse(text)
    basics = [s for s in doc.all_sections() if s.title == "Basics"]
    assert len(basics) == 3
    for i, sec in enumerate(basics, 1):
        assert [t.body[0][0] for t in doc.tables_in(sec)] == [str(i)]
        assert [d.term for d in doc.defs_in(sec)] == [f"Term{i}"]
