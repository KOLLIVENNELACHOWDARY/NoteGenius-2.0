import csv
import io
import os

from pptx.util import Inches

from conftest import MATHS, SAMPLE
from utils.flashcards import build_cards, cards_to_csv
from utils.mcq_generator import MCQGenerator
from utils.mindmap import generate_mindmaps
from utils.mnemonics import create_mnemonics
from utils.pptgen import generate_ppt
from utils.qna import get_answers
from utils.ques_gen import process_document
from utils.structure import parse
from utils.studyplan import build_plan
from utils.summary import summarize_document, to_markdown
from utils.tts import speakable


def test_flashcards_cover_every_kind_of_content():
    cards = build_cards(parse(SAMPLE), 80)
    kinds = {c["type"] for c in cards}
    assert {"definition", "formula", "variable", "table", "list", "fact"} <= kinds
    formula = next(c for c in cards if c["type"] == "formula" and "Newton" in c["front"]["text"])
    assert formula["back"]["tex"] == "F = ma" and ["F", "net force"] in formula["back"]["vars"]
    table = next(c for c in cards if c["type"] == "table")
    assert "SI Unit" in table["front"]["text"] and "newton" in table["back"]["text"] or "kilogram" in table["back"]["text"]


def test_flashcard_csv_is_anki_ready():
    rows = list(csv.reader(io.StringIO(cards_to_csv(build_cards(parse(SAMPLE), 40)))))
    assert rows[0] == ["Front", "Back", "Tags"] and len(rows) > 10
    assert any("\\(" in r[1] for r in rows[1:])


def test_quiz_questions_are_valid_for_all_types():
    questions = MCQGenerator().generate_from_document(parse(SAMPLE), 12, "medium", seed=3)
    assert {q["type"] for q in questions} >= {"definition", "formula", "symbol", "table"}
    for q in questions:
        assert q["answer"] in q["options"] and len(set(q["options"])) == len(q["options"]) >= 3
        if q["type"] == "formula":
            assert all(o in q["tex"] for o in q["options"])
    assert len({q["question"] for q in questions}) == len(questions)


def test_practice_questions_have_marks_and_answers():
    qs = process_document(parse(SAMPLE), 8, seed=1)
    assert len(qs) == 8 and all(q["marks"] and q["answer"] for q in qs)
    assert {"define", "formula"} <= {q["type"] for q in qs}


def test_qna_understands_formula_definition_and_table_questions(monkeypatch):
    monkeypatch.setenv("QA_BACKEND", "search")
    res = {r["question"]: r for r in get_answers(SAMPLE, [
        "What is the formula for kinetic energy?", "define speed", "What is the SI unit of force?", "state newton's second law"])}
    assert res["What is the formula for kinetic energy?"]["answer"] == "KE = 1/2 m v^2"
    assert res["state newton's second law"]["tex"] == "F = ma"
    assert "distance travelled" in res["define speed"]["answer"]
    assert "newton" in res["What is the SI unit of force?"]["answer"]


def test_summary_markdown_keeps_formulas_and_tables():
    result = summarize_document(SAMPLE, "standard")
    md = to_markdown(result)
    assert "`F = ma`" in md and "| Quantity | Symbol | SI Unit |" in md and "**Speed**" in md


def test_mnemonics_from_lists():
    sets = create_mnemonics(SAMPLE, seed=1)
    assert sets[0]["acronym"] == "KPT" and sets[0]["pairs"][0][0].startswith("Kinetic")


def test_speech_reads_formulas_in_words():
    text = speakable(parse(SAMPLE), "full")
    assert "v equals u plus a t" in text and "F = ma" not in text.split("Newton")[-1][:60] or "F equals m a" in text


def test_study_plan_covers_all_days():
    plan = build_plan(SAMPLE, days=5, minutes_per_day=45)
    assert len(plan["days"]) == 5 and plan["days"][-1]["focus"] == "Final check"
    assert all(d["tasks"] for d in plan["days"])
    assert build_plan(SAMPLE, days=1)["days"][0]["focus"] == "Crash course"


def test_mindmaps_render_overview_and_sections(tmp_path):
    maps = generate_mindmaps(SAMPLE, str(tmp_path))
    assert maps[0]["kind"] == "overview" and len(maps) >= 2
    for m in maps:
        assert open(os.path.join(tmp_path, m["file"]), "rb").read(4) == b"\x89PNG"


def test_powerpoint_has_typeset_formulas_native_tables_and_notes(tmp_path):
    name, count = generate_ppt(SAMPLE, str(tmp_path))
    from pptx import Presentation

    prs = Presentation(os.path.join(tmp_path, name))
    assert len(prs.slides) == count >= 12
    pictures = sum(1 for s in prs.slides for sh in s.shapes if sh.shape_type == 13)
    tables = sum(1 for s in prs.slides for sh in s.shapes if sh.has_table)
    assert pictures >= 8 and tables == 2
    assert any(s.has_notes_slide and "Source text" in s.notes_slide.notes_text_frame.text for s in prs.slides)
    # nothing hangs off the slide
    for s in prs.slides:
        for sh in s.shapes:
            assert sh.left >= 0 and sh.top >= 0 and sh.left + sh.width <= prs.slide_width + Inches(0.02) and sh.top + sh.height <= prs.slide_height + Inches(0.02)


def test_deck_for_maths_notes_has_a_formula_sheet(tmp_path):
    name, count = generate_ppt(MATHS, str(tmp_path))
    from pptx import Presentation

    titles = [sh.text_frame.text for s in Presentation(os.path.join(tmp_path, name)).slides for sh in s.shapes if sh.has_text_frame]
    assert any(t.startswith("Formula sheet") for t in titles) and count <= 70


def test_big_documents_stay_within_the_slide_cap(tmp_path):
    chunk = SAMPLE.replace("Physics Notes", "")
    big = "\n\n".join(f"# Chapter {i}\n\n{chunk}" for i in range(1, 30))
    name, count = generate_ppt(big, str(tmp_path))
    assert count <= 70


def test_qna_gives_a_different_right_answer_for_each_question(monkeypatch):
    import os
    monkeypatch.setenv("QA_BACKEND", "search")
    notes = open(os.path.join(os.path.dirname(__file__), "qa_notes.txt"), encoding="utf-8").read()
    qs = ["What is velocity?", "formula for kinetic energy", "What is the unit of power?", "explain Newton's third law",
          "what is the formula of potential energy", "equation of motion", "explan potential enrgy", "who discovered gravity"]
    ans = {r["question"]: r for r in get_answers(notes, qs)}
    assert "speed in a given direction" in ans["What is velocity?"]["answer"]
    assert ans["formula for kinetic energy"]["answer"].startswith("KE")
    assert "watt" in ans["What is the unit of power?"]["answer"]
    assert "equal and opposite" in ans["explain Newton's third law"]["answer"]
    assert ans["what is the formula of potential energy"]["answer"].startswith("PE")
    assert ans["equation of motion"]["answer"].startswith("v = u")
    assert "stored in a body" in ans["explan potential enrgy"]["answer"]  # typo tolerated
    assert ans["who discovered gravity"]["kind"] == "none"  # not in the notes: say so, do not guess
    assert len({r["answer"] for r in ans.values()}) == len(ans)


def test_key_points_questions_answer_from_the_section(monkeypatch):
    monkeypatch.setenv("QA_BACKEND", "search")
    notes = ("GOVERNMENT-FACING EXECUTIVE REFERENCE\nPurpose\nThis document gives officials a short reference on the regional economy. "
             "It explains the main sectors and how they connect.\n\n01 · EXECUTIVE SUMMARY\nThe region has a diversified economy led by "
             "manufacturing and services. Growth has been steady for five years.\n\n02 · MARKET DRIVERS\nDemand is driven by exports and public investment.\n")
    a = {r["question"]: r for r in get_answers(notes, ["What are the key points of Purpose?", "key points of market drivers",
                                                        "What are the key points of GOVERNMENT-FACING EXECUTIVE REFERENCE?"])}
    assert a["What are the key points of Purpose?"]["items"][0].startswith("This document gives officials")
    assert "exports" in a["key points of market drivers"]["items"][0]
    assert "Purpose" in a["What are the key points of GOVERNMENT-FACING EXECUTIVE REFERENCE?"]["items"]