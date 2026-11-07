"""Practice questions (with marks and model answers) built from the structure of the notes."""
import random

from .structure import Document, compress, key_points

MARKS = {"define": 2, "formula": 3, "explain": 5, "table": 3, "application": 4}


def process_document(doc, num_questions=8, seed=None):
    """Return [{'type','marks','question','answer','tex','section'}] mixing definitions, formulas, explanations and tables."""
    rng = random.Random(seed)
    pools = {"define": [], "formula": [], "explain": [], "table": [], "application": []}

    for d in doc.definitions:
        pools["define"].append({"question": f"Define {d.term}.", "answer": d.meaning, "section": d.section})

    for f in doc.formulas:
        title = f.name or next((m for s, m in f.variables if "=" in f.raw and s == f.raw.split("=")[0].strip()), "")
        q = f"State the formula for {title} and explain each symbol." if title else f"Write down what the formula  {f.raw}  represents and explain each symbol."
        ans = f.raw + ("  where " + "; ".join(f"{s} = {m}" for s, m in f.used_variables) if f.used_variables else "")
        pools["formula"].append({"question": q, "answer": ans, "tex": f.latex, "section": f.section})
        if f.variables:
            pools["application"].append({
                "question": f"Using {f.raw}, explain how a change in one quantity affects the others.",
                "answer": ans or "Relate the symbols in the formula.", "tex": f.latex, "section": f.section,
            })

    kp = key_points(doc, per_section=5)
    for sec in doc.all_sections():
        pts = kp.get(sec.uid, [])
        if len(pts) >= 2 and sec.title and sec.title != "Overview":
            pools["explain"].append({
                "question": f"Explain {sec.title}.", "answer": " ".join(compress(p, 30) for p in pts[:5]),
                "section": sec.title,
            })

    for t in doc.tables:
        if len(t.header) >= 2 and len(t.body) >= 2:
            where = t.caption or t.section
            pools["table"].append({
                "question": f"Using the table{(' ' + repr(where)) if where else ''}, compare {t.body[0][0]} and {t.body[1][0]}.",
                "answer": "; ".join(f"{r[0]}: " + ", ".join(f"{h} {v}" for h, v in zip(t.header[1:], r[1:])) for r in t.body[:2]),
                "section": t.section,
            })

    for k in pools:
        rng.shuffle(pools[k])
    out, kinds = [], [k for k in ("define", "formula", "explain", "table", "application") if pools[k]]
    while kinds and len(out) < num_questions:
        for k in list(kinds):
            if not pools[k]:
                kinds.remove(k)
                continue
            q = pools[k].pop()
            q["type"], q["marks"] = k, MARKS[k]
            out.append(q)
            if len(out) >= num_questions:
                break
    return out


def process_text_by_sentence(text, num_questions=5):
    """Backward-compatible wrapper working directly on text."""
    from .structure import parse

    return [{"question": q["question"], "source": q["answer"]} for q in process_document(parse(text), num_questions)]
