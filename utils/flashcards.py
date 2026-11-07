"""Flashcards built from the structure of the notes: definitions, formulas, table rows, lists and key facts."""
import csv
import io
import re
from itertools import zip_longest

from . import formulas as fx
from .nlp import stopword_set
from .structure import Document, key_points, parse

TYPE_LABELS = {
    "definition": "Definitions", "formula": "Formulas", "variable": "Symbols", "table": "Table facts",
    "list": "Lists", "fact": "Key facts",
}


def _formula_title(f):
    if f.name:
        return f.name
    lhs = f.raw.split("=")[0].strip() if "=" in f.raw else ""
    for sym, meaning in f.variables:
        if sym == lhs:
            return meaning
    return ""


def _blank_term(sentence, doc_terms):
    """Replace the most informative term in a sentence with a blank. Returns (question, answer) or None."""
    stop = stopword_set()
    for term in doc_terms:
        m = re.search(r"\b" + re.escape(term) + r"\b", sentence, re.I)
        if m:
            return sentence[: m.start()] + "_____" + sentence[m.end():], m.group(0)
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{5,}", sentence) if w.lower() not in stop]
    if not words:
        return None
    ans = max(words, key=len)
    return re.sub(r"\b" + re.escape(ans) + r"\b", "_____", sentence, count=1), ans


def build_cards(doc, limit=80):
    """Return a list of card dicts: {id, type, section, front{text,tex}, back{text,tex,vars}}."""
    pools = {k: [] for k in ("formula", "definition", "table", "list", "variable", "fact")}

    for d in doc.definitions:
        pools["definition"].append({
            "type": "definition", "section": d.section,
            "front": {"text": f"What is {d.term}?"}, "back": {"text": d.meaning},
        })

    for f in doc.formulas:
        title = _formula_title(f)
        used = f.used_variables
        front = f"What is the formula for {title}?" if title else "Complete the formula: " + (f.raw.split("=")[0].strip() + " = ?" if "=" in f.raw else "recall the formula")
        pools["formula"].append({
            "type": "formula", "section": f.section, "front": {"text": front},
            "back": {"text": f.raw, "tex": f.latex, "vars": [list(v) for v in used]},
        })
        for sym, meaning in used[:4]:
            pools["variable"].append({
                "type": "variable", "section": f.section,
                "front": {"text": f"In  {f.raw}  what does \"{sym}\" stand for?", "tex": None, "formula_tex": f.latex},
                "back": {"text": meaning},
            })

    for t in doc.tables:
        if len(t.header) < 2:
            continue
        for row in t.body[:14]:
            if not row[0].strip() or not any(c.strip() for c in row[1:]):
                continue
            facts = [f"{h}: {v}" for h, v in zip(t.header[1:], row[1:]) if v.strip()]
            where = t.caption or t.section
            pools["table"].append({
                "type": "table", "section": t.section,
                "front": {"text": f"For {t.header[0]} “{row[0]}”: what are the " + " and ".join(h for h, v in zip(t.header[1:], row[1:]) if v.strip()) + "?"
                          + (f"  (table: {where})" if where else "")},
                "back": {"text": "\n".join(facts)},
            })

    for sec, b in doc.lists:
        items = [i for i in b["items"] if not fx.looks_like_equation(i)]
        if 3 <= len(items) <= 9:
            label = b.get("label") or f"the key points of {sec.title}"
            pools["list"].append({
                "type": "list", "section": sec.title,
                "front": {"text": f"List the {len(items)} items: {label}"}, "back": {"text": "\n".join("• " + i for i in items)},
            })

    terms = sorted({d.term for d in doc.definitions}, key=len, reverse=True)
    kp = key_points(doc, per_section=3, max_words=30)
    titles = {s.uid: s.title for s in doc.all_sections()}
    for uid, pts in kp.items():
        sec = titles.get(uid, "")
        for p in pts:
            if p.startswith("Key items:") or ": " in p[:60] and ";" in p:
                continue
            blank = _blank_term(p.rstrip("…"), terms)
            if blank and len(p.split()) >= 7:
                q, ans = blank
                pools["fact"].append({"type": "fact", "section": sec, "front": {"text": q}, "back": {"text": ans}})

    order = ["formula", "definition", "table", "list", "variable", "fact"]
    caps = {"formula": 0.30, "definition": 0.35, "table": 0.15, "list": 0.07, "variable": 0.08, "fact": 0.12}
    take = {k: min(len(pools[k]), max(1, int(limit * caps[k]) + 1)) for k in order if pools[k]}
    cards, seen = [], set()
    for batch in zip_longest(*[pools[k][: take[k]] for k in order if k in take]):
        for c in batch:
            if c and len(cards) < limit:
                key = (c["type"], c["front"]["text"])
                if key not in seen:
                    seen.add(key)
                    cards.append(c)
    for i, c in enumerate(cards):
        c["id"] = f"c{i}"
    # keep the notes' own order inside the deck so related cards sit together
    return cards


def cards_to_csv(cards):
    """CSV for Anki/Quizlet import: Front, Back, Tags. Formulas use \\( \\) so Anki renders them."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Front", "Back", "Tags"])
    for c in cards:
        front = c["front"]["text"]
        if c["front"].get("formula_tex"):
            front += "  \\(" + c["front"]["formula_tex"] + "\\)"
        back = c["back"]["text"]
        if c["back"].get("tex"):
            back = "\\(" + c["back"]["tex"] + "\\)"
            if c["back"].get("vars"):
                back += "\n" + "\n".join(f"{s} = {m}" for s, m in c["back"]["vars"])
        tag = re.sub(r"\W+", "_", c["type"] + " " + (c["section"] or "notes")).strip("_")
        w.writerow([front, back, tag])
    return buf.getvalue()
