"""Notebook-style outputs built only from your sources (no outside facts): suggested questions, briefing document,
study guide, FAQ, timeline and an audio-overview script for two hosts."""
import re

from . import formulas as fx
from .nlp import split_sentences
from .structure import compress, key_points, parse, top_sentences
from .summary import summarize_document

YEAR = re.compile(r"\b(1[0-9]{3}|20[0-9]{2})\b")


def _end(s):
    s = s.strip()
    return s if s.endswith((".", "!", "?")) else s.rstrip("…") + "."


def _vars(f):
    return "; ".join(f"{s} = {m}" for s, m in f.used_variables)


def suggested_questions(doc, n=6):
    qs = []
    for d in doc.definitions[:3]:
        qs.append(f"What is {d.term.lower() if d.term[1:2].islower() else d.term}?")
    for f in [f for f in doc.formulas if f.name][:2]:
        qs.append(f"What is the formula for {f.name.lower()}?")
    for sec in doc.sections[:3]:
        if sec.title:
            qs.append(f"What are the key points of {sec.title}?")
    seen, out = set(), []
    for q in qs:
        if q.lower() not in seen:
            seen.add(q.lower())
            out.append(q)
    return out[:n]


def source_guide(text, name=""):
    """What a source covers: a short summary, the main topics, and questions worth asking."""
    doc = parse(text)
    topics = [s.title for s in doc.all_sections() if s.title and s.level == 1][:8] or [s.title for s in doc.all_sections() if s.title][:8]
    return {"name": name, "summary": top_sentences(doc, 3, 28), "topics": topics, "questions": suggested_questions(doc, 4),
            "stats": doc.stats()}


# ---------------------------------------------------------------- guides
def briefing(text):
    s = summarize_document(text, "standard")
    return {"title": s["title"], "overview": s["overview"], "sections": s["sections"], "terms": s["definitions"][:12],
            "formulas": s["formulas"][:10], "stats": s["stats"], "minutes": s["minutes"]}


def study_guide(text):
    doc = parse(text)
    kp = key_points(doc, per_section=3)
    short = []
    for d in doc.definitions[:6]:
        short.append({"q": f"Define {d.term}.", "a": _end(d.meaning)})
    for f in [f for f in doc.formulas if f.name][:3] + [f for f in doc.formulas if not f.name][:1]:
        short.append({"q": f"State the formula for {f.name.lower() if f.name else 'the relation shown'} and explain each symbol.",
                      "a": f.raw + (f"  ({_vars(f)})" if f.used_variables else ""), "tex": f.latex})
    for sec in doc.sections:
        pts = kp.get(sec.uid, [])
        if sec.title and pts:
            short.append({"q": f"Explain the main ideas of {sec.title}.", "a": " ".join(_end(p) for p in pts[:2])})
    essay = [f"Discuss {s.title} and give one example from your notes." for s in doc.sections if s.title][:4]
    if len(doc.definitions) >= 2:
        essay.append(f"Compare {doc.definitions[0].term} and {doc.definitions[1].term}.")
    return {"title": doc.title, "short": short[:12], "essay": essay, "glossary": [(d.term, d.meaning) for d in doc.definitions],
            "stats": doc.stats()}


def faq(text):
    doc = parse(text)
    kp = key_points(doc, per_section=3)
    items = []
    for d in doc.definitions[:6]:
        items.append({"q": f"What is {d.term}?", "a": _end(d.meaning), "where": d.section})
    for f in [f for f in doc.formulas if f.name][:4]:
        items.append({"q": f"What is the formula for {f.name.lower()}?", "a": f.raw, "tex": f.latex, "extra": _vars(f), "where": f.section})
    for f in [f for f in doc.formulas if f.used_variables][:3]:
        sym, meaning = f.used_variables[0]
        items.append({"q": f"What does {sym} stand for in {f.name or f.raw}?", "a": _end(meaning), "where": f.section})
    for sec in doc.all_sections():
        pts = kp.get(sec.uid, [])
        if sec.title and pts and sec.level <= 2:
            items.append({"q": f"What are the key points of {sec.title}?", "a": " ".join(_end(p) for p in pts[:3]), "where": sec.title})
    for t in doc.tables[:3]:
        label = t.caption or t.section
        if label and t.body:
            items.append({"q": f"What does the table \"{label}\" show?", "a": f"It compares {', '.join(t.header)}. For example: " +
                          "; ".join(f"{h} {v}" for h, v in zip(t.header, t.body[0]) if v) + ".", "where": t.section})
    return {"title": doc.title, "items": items[:18]}


def timeline(text):
    doc = parse(text)
    events, seen = [], set()
    for sec in doc.all_sections():
        units = []
        for b in sec.blocks:
            if b["kind"] in ("para", "note", "example"):
                units += split_sentences(b["text"])
            elif b["kind"] == "list":
                units += b["items"]
        for u in units:
            if fx.looks_like_equation(u) and "=" in u:
                continue
            m = YEAR.search(u)
            if m and len(u.split()) >= 4 and u.lower() not in seen:
                seen.add(u.lower())
                events.append({"year": int(m.group(1)), "text": compress(u, 34), "section": sec.title})
    events.sort(key=lambda e: e["year"])
    return {"title": doc.title, "events": events[:40]}


def to_markdown(kind, data):
    out = [f"# {data.get('title', 'Notes')}", ""]
    if kind == "briefing":
        out += ["## Overview", ""] + [f"- {s}" for s in data["overview"]]
        for sec in data["sections"]:
            out += ["", f"## {sec['title']}", ""] + [f"- {p}" for p in sec["points"]]
        if data["terms"]:
            out += ["", "## Key terms", ""] + [f"- **{d.term}**: {d.meaning}" for d in data["terms"]]
        if data["formulas"]:
            out += ["", "## Formulas", ""] + [f"- {(f.name + ': ') if f.name else ''}`{f.raw}`" for f in data["formulas"]]
    elif kind == "studyguide":
        out += ["## Short-answer questions", ""]
        for i, q in enumerate(data["short"], 1):
            out.append(f"{i}. {q['q']}")
        out += ["", "## Answer key", ""]
        for i, q in enumerate(data["short"], 1):
            out.append(f"{i}. {q['a']}")
        out += ["", "## Essay questions", ""] + [f"{i}. {q}" for i, q in enumerate(data["essay"], 1)]
        out += ["", "## Glossary", ""] + [f"- **{t}**: {m}" for t, m in data["glossary"]]
    elif kind == "faq":
        for it in data["items"]:
            out += [f"### {it['q']}", "", it["a"] + (f" ({it['extra']})" if it.get("extra") else ""), ""]
    elif kind == "timeline":
        out += [f"- **{e['year']}**: {e['text']}" for e in data["events"]]
    return "\n".join(out) + "\n"


# ------------------------------------------------------- audio overview
_OPENERS = ["First up, {t}.", "Let's start with {t}.", "Next, let's talk about {t}.", "Moving on to {t}.", "Now for {t}.", "Another big idea: {t}."]
_REACT = ["That makes sense.", "Good to know.", "Right, that's an important one.", "Okay, I like that.", "That's worth remembering."]


def audio_script(text, length="short"):
    """A two-host conversation about the notes, using only what the notes say."""
    doc = parse(text)
    kp = key_points(doc, per_section=3)
    secs = [s for s in doc.all_sections() if s.title and (kp.get(s.uid) or doc.defs_in(s) or doc.formulas_in(s))]
    limit = 6 if length == "long" else 3
    secs = secs[:limit]
    A, B = "Alex", "Sam"
    turns = []

    def say(who, line):
        line = re.sub(r"\s+", " ", line).strip()
        if line:
            turns.append({"who": "A" if who == A else "B", "name": who, "text": line})

    names = ", ".join(s.title for s in secs[:-1]) + (" and " if len(secs) > 1 else "") + secs[-1].title if secs else doc.title
    what = "your notes" if doc.title in ("Study notes", "") else doc.title
    say(A, f"Welcome to your audio overview of {what}. Today we're covering {names}.")
    say(B, "Let's dive in. I'll keep it simple and stick to what your notes say.")
    for i, sec in enumerate(secs):
        say(A, _OPENERS[i % len(_OPENERS)].format(t=sec.title))
        pts = [p for p in kp.get(sec.uid, [])]
        defs, fs = doc.defs_in(sec), doc.formulas_in(sec)
        if pts:
            say(B, _end(pts[0]))
        if defs:
            d = defs[0]
            say(A, f"And what does {d.term.lower() if d.term[1:2].islower() else d.term} mean?")
            say(B, f"{d.term} is {_end(d.meaning[0].lower() + d.meaning[1:] if d.meaning[:2].islower() else d.meaning)}")
        if fs:
            f = fs[0]
            say(A, "Is there a formula to remember?")
            extra = (" Here, " + ", ".join(f"{s} is {m}" for s, m in f.used_variables[:4]) + ".") if f.used_variables else ""
            say(B, f"Yes. {(f.name + ' is ') if f.name else ''}{f.speech}.{extra}")
        elif len(pts) > 1:
            say(A, _REACT[i % len(_REACT)])
            say(B, _end(pts[1]))
    tops = [t for t in top_sentences(doc, 6, 30) if "=" not in t and not fx.looks_like_equation(t)]
    say(A, "To wrap up, here is the main thing to take away. " + (_end(tops[0]) if tops else ""))
    say(B, "Great. Go through the flashcards and the quiz next to lock it in.")
    return turns


def audio_mp3(turns, out_dir, lang="en", max_turns=22):
    """Concatenate one gTTS clip per turn, using a different accent per host (needs internet)."""
    import io
    import os
    import uuid

    from gtts import gTTS

    buf = io.BytesIO()
    try:
        for t in turns[:max_turns]:
            tld = "com" if t["who"] == "A" else "co.uk"
            if lang != "en":
                tld = "com"
            gTTS(text=t["text"][:1500], lang=lang, tld=tld).write_to_fp(buf)
    except Exception as exc:
        raise RuntimeError("The text-to-speech service could not be reached. Use 'Listen in your browser' instead.") from exc
    os.makedirs(out_dir, exist_ok=True)
    name = f"speech_{uuid.uuid4().hex}.mp3"
    with open(os.path.join(out_dir, name), "wb") as fh:
        fh.write(buf.getvalue())
    return name
