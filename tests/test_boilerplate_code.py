"""Headers, footers, college names and front matter are dropped; programs stay code and never become formulas."""
import os

import pytest

from utils import code, structure as st
from utils.boilerplate import strip_boilerplate
from utils.extract import extract_with_report
from conftest import token

HERE = os.path.dirname(os.path.abspath(__file__))

COLLEGE = """SRI VENKATESWARA COLLEGE OF ENGINEERING
(Autonomous) Affiliated to JNTU Hyderabad
Department of Computer Science and Engineering

Prepared by: Dr. K. Ramesh, Assistant Professor
Academic Year: 2023-24
Roll No: 21B81A0512

CERTIFICATE
This is to certify that the project work is a bonafide work carried out by the student.
Signature of Guide        Head of the Department

ACKNOWLEDGEMENT
I would like to express my sincere gratitude to my guide for the support.

CONTENTS
1. Introduction ........ 3
2. Stacks ........ 5

# Stacks

A stack is a linear data structure that follows the LIFO principle, where the last element inserted is the first removed.
SRI VENKATESWARA COLLEGE OF ENGINEERING | Unit II | Page 4

Push adds an element and pop removes the top element from the stack structure.

Page 5
SRI VENKATESWARA COLLEGE OF ENGINEERING | Unit II | Page 6

Velocity is v = u + at where u is the initial velocity.
"""


def test_college_cover_certificate_contents_and_running_headers_are_dropped():
    out, removed = strip_boilerplate(COLLEGE)
    for junk in ("SRI VENKATESWARA", "Prepared by", "Roll No", "CERTIFICATE", "bonafide", "ACKNOWLEDGEMENT", "CONTENTS",
                 "Introduction ...", "Page 5", "Unit II"):
        assert junk not in out, junk
    assert "A stack is a linear data structure" in out and "Velocity is v = u + at" in out
    assert removed


def test_real_content_that_mentions_a_department_or_university_is_kept():
    text = ("# Governance\n\nThe Department of Defense is a government body that buys software for the military services.\n\n"
            "Harvard University was founded in 1636 and is the oldest institution of higher learning in the United States.\n\n"
            "- Institute of Radio Engineers merged into the IEEE in 1963\n\nA body of mass m has weight W = mg near the surface.\n")
    out, removed = strip_boilerplate(text)
    assert out.strip() == text.strip() and removed == []


def test_nothing_is_removed_when_it_would_leave_no_notes():
    text = "Department of Physics\nProf. A Kumar\nRoll No: 12\nPage 1\n"
    assert strip_boilerplate(text)[0] == text


@pytest.mark.parametrize("snippet,lang", [
    ('#include <stdio.h>\nint main() {\n    int a = 5;\n    printf("%d", a);\n    return 0;\n}', "c"),
    ("def add(a, b):\n    c = a + b\n    return c\n\nprint(add(2, 3))", "python"),
    ("public class Hello {\n    public static void main(String[] args) {\n        System.out.println(\"Hi\");\n    }\n}", "java"),
    ("SELECT name, age\nFROM students\nWHERE age > 18;", "sql"),
])
def test_programs_become_one_code_block_not_formulas(snippet, lang):
    doc = st.parse("# Programs\n\nHere is the program.\n\n" + snippet + "\n\nThat is all about it, and the output is printed.\n")
    blocks = [b for s in doc.all_sections() for b in s.blocks]
    codes = [b for b in blocks if b["kind"] == "code"]
    assert len(codes) == 1 and codes[0]["lang"] == lang
    assert codes[0]["text"].strip() == snippet.strip()
    assert doc.formulas == [] and doc.definitions == []


def test_fenced_code_keeps_hash_comments_and_is_not_a_heading():
    doc = st.parse("# Notes\n\n```python\n# a comment\nx = 5\ny = x * 2\n```\n\nDone with it all here.\n")
    assert [s.title for s in doc.all_sections()] == ["Notes"]
    assert doc.codes[0][1]["text"] == "# a comment\nx = 5\ny = x * 2"
    assert doc.formulas == []


@pytest.mark.parametrize("line", ["v = u + at", "y = sin(x)", "PV = nRT", "E = mc^2", "F = ma", "x^{2}", "KE = 1/2 mv^2", "v = u + at;"])
def test_formulas_are_not_mistaken_for_code(line):
    assert code.line_score(line) < 2
    if line != "x^{2}":
        assert st._is_formula_line(line)


@pytest.mark.parametrize("line", ["int a = 5;", "for (i = 0; i < n; i++) {", "print('hi')", "if x > 3:", "return a + b;", "i += 1"])
def test_statements_are_not_formulas(line):
    from utils import formulas as fx
    assert code.line_score(line) >= 2
    assert not fx.looks_like_equation(line)


def test_pdf_with_college_header_footer_and_code():
    text, ignored = extract_with_report(os.path.join(HERE, "sample_college.pdf"))
    assert "COLLEGE" not in text and "Page " not in text and "Prepared by" not in text and "Roll No" not in text
    assert "```" in text and "#include <stdio.h>" in text and "    int a = 5;" in text
    doc = st.parse(text)
    assert {f.raw for f in doc.formulas} == {"T = n * c", "KE = 1/2 mv^2", "v = u + at"}
    assert len(doc.codes) == 1 and doc.codes[0][1]["text"].rstrip().endswith("}")
    assert ignored


def test_docx_cover_is_dropped_and_monospace_paragraphs_become_code():
    text, _ = extract_with_report(os.path.join(HERE, "sample_college.docx"))
    assert "COLLEGE" not in text and "CERTIFICATE" not in text and "Prepared by" not in text
    doc = st.parse(text)
    assert len(doc.codes) == 1 and "print(add(2, 3))" in doc.codes[0][1]["text"]
    assert [f.raw for f in doc.formulas] == ["s = ut + 1/2 at^2"]


def test_every_tool_works_on_notes_with_code_and_never_quizzes_the_code(client):
    notes = open(os.path.join(HERE, "sample_physics.txt"), encoding="utf-8").read() + """

# Programming in C

A variable is a named storage location that holds a value while the program runs.

```c
#include <stdio.h>
int main() {
    int secret_marker_zz = 5;
    printf("%d", secret_marker_zz);
    return 0;
}
```

An array is a collection of elements of the same type stored in contiguous memory.
"""
    client.post("/text_input", data={"input_text": notes, "csrf_token": token(client)})
    assert "Code found" in client.get("/overview").get_data(as_text=True)
    for path in ("/summary", "/flashcards", "/formulas", "/glossary", "/cheatsheet", "/studyplan", "/qgen", "/mindmap", "/mnemonics", "/ppt",
                 "/qna", "/mcq", "/suggestions", "/summary.md", "/flashcards.csv"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        if path in ("/flashcards", "/flashcards.csv", "/glossary", "/formulas", "/qgen", "/mcq"):
            assert "secret_marker_zz" not in resp.get_data(as_text=True), path
    assert "secret_marker_zz" in client.get("/summary").get_data(as_text=True)


def test_non_latin_prose_not_swallowed_into_formula():
    from utils.structure import parse
    doc = parse("వేగం అంటే దూరం మరియు సమయం మధ్య నిష్పత్తి వివరణ\nv = d/t\n")
    raws = [f.raw for f in doc.formulas]
    assert raws and all("వేగం" not in r for r in raws)


def test_unicode_minus_equation_detected():
    from utils.formulas import looks_like_equation
    assert looks_like_equation("ΔG = ΔH − TΔS")
