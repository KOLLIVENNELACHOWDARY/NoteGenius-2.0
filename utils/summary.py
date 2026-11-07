"""Structured summaries: overview, key points per section, key terms, formulas and tables.

Extractive by default (fast, no model, never invents facts). SUMMARY_BACKEND=transformer adds an
abstractive paragraph on top when the ML extras are installed.
"""
import logging
import os
import re
from functools import lru_cache

from .structure import Document, compress, key_points, parse, reading_minutes, top_sentences

log = logging.getLogger(__name__)
LEVELS = {"brief": (3, 2), "standard": (5, 4), "detailed": (8, 6)}


@lru_cache(maxsize=1)
def _pipeline():
    from transformers import pipeline

    return pipeline("summarization", model=os.environ.get("SUMMARY_MODEL", "sshleifer/distilbart-cnn-12-6"), device=-1)


def _abstractive(text):
    pipe = _pipeline()
    words = text.split()
    chunks = [" ".join(words[i:i + 600]) for i in range(0, min(len(words), 3600), 600)]
    return " ".join(pipe(c, max_length=130, min_length=30, do_sample=False, truncation=True)[0]["summary_text"].strip() for c in chunks)


def summarize_document(text, level="standard"):
    """Return a dict with overview, sections, definitions, formulas, tables and stats."""
    doc = parse(text)
    n_overview, per_section = LEVELS.get(level, LEVELS["standard"])
    kp = key_points(doc, per_section=per_section)
    method = "extractive"
    overview = top_sentences(doc, n_overview)
    if os.environ.get("SUMMARY_BACKEND", "extractive").lower() == "transformer":
        try:
            overview = [_abstractive(text)]
            method = "transformer"
        except Exception as exc:
            log.warning("Transformer summary failed, using extractive: %s", exc)
    sections = []
    for sec in doc.all_sections():
        if not sec.title:
            continue
        pts = kp.get(sec.uid, [])
        defs = doc.defs_in(sec)
        fs = doc.formulas_in(sec)
        ts = doc.tables_in(sec)
        cs = sec.own("code")
        if pts or defs or fs or ts or cs:
            sections.append({"title": sec.title, "level": sec.level, "points": pts, "definitions": defs, "formulas": fs, "tables": ts, "code": cs})
    return {
        "title": doc.title, "overview": overview, "method": method, "sections": sections,
        "definitions": doc.definitions, "formulas": doc.formulas, "tables": doc.tables,
        "stats": doc.stats(), "minutes": reading_minutes(doc),
    }


def to_markdown(result):
    lines = [f"# {result['title']}", "", "## Overview", ""]
    lines += [f"- {s}" for s in result["overview"]]
    for sec in result["sections"]:
        lines += ["", f"## {sec['title']}", ""]
        lines += [f"- {p}" for p in sec["points"]]
        for d in sec["definitions"]:
            lines.append(f"- **{d.term}**: {d.meaning}")
        for f in sec["formulas"]:
            lines.append(f"- {(f.name + ': ') if f.name else ''}`{f.raw}`" + (f"  (where {', '.join(f'{s} = {m}' for s, m in f.used_variables)})" if f.used_variables else ""))
        for t in sec["tables"]:
            lines += ["", "| " + " | ".join(t.header) + " |", "|" + "---|" * len(t.header)]
            lines += ["| " + " | ".join(r) + " |" for r in t.body]
        for c in sec.get("code", []):
            lines += ["", "```" + (c["lang"] if c["lang"] != "code" else ""), c["text"], "```"]
    return "\n".join(lines) + "\n"
