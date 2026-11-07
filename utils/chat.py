"""Chat with your sources: every answer is built from passages in the sources and cites them as [1], [2] ... Nothing is invented."""
from . import qna
from .structure import parse

NOTHING = "I couldn't find that in your sources. Try other words, or add a source that covers it."


def _root(sec):
    while sec.parent is not None:
        sec = sec.parent
    return sec


def _snippet(unit):
    t = unit["text"]
    if unit.get("items"):
        t = "; ".join(unit["items"])
    return t if len(t) <= 240 else t[:237].rstrip() + "…"


def answer(text, question, multi=False):
    doc = parse(text)
    units = qna._units(doc)
    secs = {s.uid: s for s in doc.all_sections()}
    for u in units:
        s = secs.get(u.get("sid"))
        u["root"] = _root(s).title if (s is not None and multi) else ""
    ranked = qna._rank(units, question, k=4) if units else []
    if not ranked:
        topics = qna._topics(doc)
        hint = (" You could ask about: " + ", ".join(topics) + ".") if topics else ""
        return {"q": question, "a": NOTHING + hint, "cites": [], "also": []}
    best, shown = qna.present_best(ranked)
    cites, also, seen = [], [], set()

    def cite(u):
        key = (u["text"][:60], u["section"])
        if key in seen:
            return None
        seen.add(key)
        c = {"n": len(cites) + 1, "source": u.get("root", ""), "section": u["section"], "text": _snippet(u)}
        cites.append(c)
        return c["n"]

    n = cite(best)
    for u, _ in ranked[1:]:
        if u["text"] in best["text"] or best["text"] in u["text"]:
            continue
        k = cite(u)
        if k and len(also) < 2:
            also.append({"n": k, "text": _snippet(u)})
    return {"q": question, "a": shown["answer"], "items": shown.get("items"),
            "tex": shown.get("tex") if shown["kind"] == "formula" else None,
            "tex2": shown.get("tex") if shown["kind"] != "formula" else None, "raw2": shown.get("raw", ""), "extra": shown.get("extra", ""), "n": n, "cites": cites, "also": also}