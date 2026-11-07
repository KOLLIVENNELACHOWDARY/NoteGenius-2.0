"""Answer questions from the notes: definitions, formulas, table rows and sentences.

Uses a small neural QA model when the ML extras are installed; otherwise it ranks passages with TF-IDF.
"""
import logging
import os
import re
from functools import lru_cache

from . import formulas as fx
from .nlp import split_sentences
from .structure import Document, parse

log = logging.getLogger(__name__)
NO_ANSWER = "No answer found in your notes."


_WH = {"what", "which", "who", "whom", "whose", "when", "where", "why", "how", "does", "do", "did", "is", "are", "was", "were",
       "tell", "give", "show", "please", "explain", "describe", "define", "definition", "meaning", "mean", "means", "state",
       "formula", "formulas", "equation", "expression", "relation", "unit", "units", "symbol", "symbols", "called", "name",
       "notes", "note", "about", "types", "type", "kinds", "kind", "list", "steps", "step", "stand", "denote", "represent",
       "between", "difference", "key", "main", "important", "point", "points", "summary", "summarize", "summarise", "overview",
       "brief", "short", "detail", "details", "idea", "ideas", "topic", "concept", "concepts", "everything", "all", "mention",
       "mentioned", "cover", "covered", "tell", "can", "could", "would", "should", "me", "i", "you", "calculate", "find", "write"}
_KEEP = frozenset("first second third fourth fifth one two three four five six seven eight nine ten eleven twelve zero full "
                  "fire front system part bottom top side".split())
_stemmer = None


def _stem(w):
    global _stemmer
    if _stemmer is None:
        from nltk.stem.porter import PorterStemmer
        _stemmer = PorterStemmer()
    return _stemmer.stem(w)


def _words(text):
    return re.findall(r"[A-Za-z][A-Za-z']*|\d+", text.lower().replace("\u2019", "'"))


def _content_stems(text, drop=_WH):
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
    SW = ENGLISH_STOP_WORDS - _KEEP
    out = []
    for w in _words(text):
        w = re.sub(r"'s$", "", w).replace("'", "")
        if not w or w in SW or w in drop:
            continue
        out.append(_stem(w))
    return out


_OVERVIEW = re.compile(r"\b(key|main|important|major|short|brief)\s+(points?|ideas?|concepts?|takeaways?|facts?)\b|\b(summar\w+|overview|"
                       r"what('?s| is| are)? .*\babout|cover(ed)?|mention(ed)?|revise|revision)\b|\bpoints? (of|on|about)\b", re.I)


def _intent(q):
    ql = q.lower().strip()
    if _OVERVIEW.search(ql) and not re.search(r"\b(formula|equation|unit|symbol)\b", ql):
        return "overview"
    if re.search(r"\b(formula|equation|expression|relation|calculate)\b", ql):
        return "formula"
    if re.search(r"\b(units?|symbols?|measured in|denote|stands? for|represents?)\b", ql):
        return "unit"
    if re.search(r"\b(types?|kinds?|list|steps?|advantages?|disadvantages?|examples?|features?|characteristics|properties)\b", ql):
        return "list"
    if re.match(r"^(what|who)\b.*\b(is|are|was)\b|^define\b|^meaning of|\bmeaning\b|^explain\b|^describe\b|\bdefinition\b", ql):
        return "define"
    if re.search(r"\b(state|law|theorem|principle)\b", ql):
        return "law"
    return "general"


def _abbrev_terms(raw, terms):
    """'KE = ...' belongs to 'Kinetic energy' (initials match); 'F = ma' to 'Force'."""
    m = re.match(r"^\s*\\?([A-Za-z]{1,4})(?:_\{?\w+\}?)?\s*=", raw)
    if not m:
        return ""
    lhs = m.group(1).lower()
    out = []
    for t in terms:
        ws = re.findall(r"[A-Za-z]+", t)
        if ws and (("".join(w[0] for w in ws).lower() == lhs) or (len(lhs) == 1 and len(ws) == 1 and ws[0].lower().startswith(lhs))):
            out.append(t)
    return " ".join(out[:2])


def _units(doc):
    units = []
    covered = set()
    for sec in doc.all_sections():
        items = []
        for b in sec.blocks:
            if b["kind"] == "list":
                items += [i for i in b["items"]]
            elif b["kind"] in ("para", "note"):
                items += [x for x in split_sentences(b["text"]) if not re.match(r"^(where|here)\b", x, re.I)]
        items = [i if len(i) <= 220 else i[:217].rstrip() + "…" for i in items][:6]
        if sec.title and items:
            label = re.sub(r"^[\d.\s·•\-–—)]+", "", sec.title).strip() or sec.title
            units.append({"kind": "section", "text": label + ". " + " ".join(items), "key": label, "items": items,
                          "section": sec.title, "sid": sec.uid, "level": sec.level})
    titles = [x.title for x in doc.all_sections() if x.title and x.level <= 1]
    if doc.title and titles:
        units.append({"kind": "section", "text": doc.title + ". " + " ".join(titles), "key": doc.title, "items": titles[:10],
                      "section": doc.title, "sid": "", "level": 0, "overall": True})
    for d in doc.definitions:
        units.append({"kind": "definition", "text": f"{d.term}: {d.meaning}", "key": d.term, "section": d.section, "sid": d.sid})
        covered.add(re.sub(r"\W+", " ", d.meaning.lower()).strip()[:60])
    fobj = {(f.sid, f.raw): f for f in doc.formulas}
    terms = [d.term for d in doc.definitions] + [t.body[i][0] for t in doc.tables for i in range(len(t.body)) if t.body[i]]
    placed = set()
    for sec in doc.all_sections():
        last, last_text = None, ""
        for b in sec.blocks:
            kind = b["kind"]
            if kind in ("para", "note", "example"):
                for s in split_sentences(b["text"]):
                    norm = re.sub(r"\W+", " ", s.lower())
                    if any(c and c in norm for c in covered) and not re.match(r"^(where|here|if)\b", s, re.I):
                        last, last_text = None, s
                        continue
                    u = {"kind": "sentence", "text": s, "key": s[:40], "section": sec.title, "sid": sec.uid,
                         "vars": bool(re.match(r"^(where|here|here,|in which|such that)\b", s, re.I))}
                    units.append(u)
                    last, last_text = u, s
            elif kind == "list":
                items = list(b["items"])
                for it in items:
                    units.append({"kind": "sentence", "text": (b["label"] + ": " if b["label"] else "") + it, "key": b["label"] or it[:40],
                                  "section": sec.title, "sid": sec.uid, "group": {"label": b["label"], "items": items}})
                last, last_text = None, (b["label"] or "")
            elif kind == "formula":
                f = fobj.get((sec.uid, b["raw"]))
                if f is None:
                    continue
                placed.add(id(f))
                abbr = _abbrev_terms(f.raw, terms)
                near = " ".join(x for x in (f.name, abbr or last_text, sec.title) if x).strip()
                vars_ = ", ".join(f"{s} = {m}" for s, m in f.used_variables)
                units.append({"kind": "formula", "text": f"{near} {f.raw} {vars_}".strip(), "key": f.name or abbr or last_text[:60] or f.raw,
                              "formula": f, "section": f.section, "sid": f.sid, "name": f.name, "near": near})
                if last is not None and "formula" not in last:
                    last["formula"] = f
    for f in doc.formulas:
        if id(f) in placed:
            continue
        vars_ = ", ".join(f"{s} = {m}" for s, m in f.used_variables)
        label = f.name or (f.context[:80] if f.context else "")
        units.append({"kind": "formula", "text": f"{label} {f.raw} {vars_}".strip(), "key": f.name or f.raw, "formula": f,
                      "section": f.section, "sid": f.sid, "name": f.name, "near": label})
    for t in doc.tables:
        for row in t.body:
            cells = "; ".join(f"{h}: {v}" for h, v in zip(t.header, row) if v)
            units.append({"kind": "table", "text": f"{t.caption} {cells}".strip(), "key": row[0], "section": t.section, "table": t, "row": row, "sid": t.sid})
    return units


@lru_cache(maxsize=1)
def _pipeline():
    from transformers import pipeline

    try:
        import torch

        device = 0 if torch.cuda.is_available() else -1
    except ImportError:
        device = -1
    return pipeline("question-answering", model=os.environ.get("QA_MODEL", "deepset/tinyroberta-squad2"), device=device)


def _match(stem, vocab):
    """True if the stem is in vocab, or is a close misspelling of a word in it."""
    if stem in vocab:
        return True
    if len(stem) >= 5:
        from rapidfuzz import fuzz
        return any(len(v) >= 5 and fuzz.ratio(stem, v) >= 86 for v in vocab)
    return False


def _rank(units, question, k=3):
    """Best units for the question. Returns [] when the notes do not really cover it."""
    focus = list(dict.fromkeys(_content_stems(question)))
    intent = _intent(question)
    if not focus and intent == "overview":
        tops = [u for u in units if u["kind"] == "section" and u.get("level", 1) <= 1] or [u for u in units if u["kind"] == "section"]
        return [({"kind": "section", "text": "Your notes", "key": "Your notes", "section": "All sections", "sid": "",
                  "items": [u["key"] for u in tops[:10]], "overall": True}, 1.0)] if tops else []
    if not focus or not units:
        return []
    n = len(units)
    toks = [set(_content_stems(u["text"], drop=set())) for u in units]
    df = {}
    for ts in toks:
        for t in ts:
            df[t] = df.get(t, 0) + 1
    import math
    idf = {f: math.log(1 + n / (1 + df.get(f, 0))) + 0.5 for f in focus}
    total = sum(idf.values())
    symbol_q = bool(re.search(r"\b(stand|symbol|denote|represent)", question.lower()))
    scored = []
    for u, ts in zip(units, toks):
        kt = set(_content_stems(str(u.get("key") or ""), drop=set()))
        nt = set(_content_stems(u.get("near", ""), drop=set())) if u.get("near") else set()
        hit = [f for f in focus if _match(f, ts)]
        if not hit:
            continue
        cover = sum(idf[f] for f in hit) / total
        score = cover
        if kt and all(f in kt or _match(f, kt) for f in focus):
            score += 0.45
        elif kt and kt <= set(focus):
            score += 0.3
        kind = u["kind"]
        if intent == "formula" and kind in ("definition", "table"):
            score *= 0.75
        if intent == "define":
            if kind == "definition":
                score += 0.35
            elif kind == "sentence" and re.match(r"^(an?\s+|the\s+)?" + re.escape(u["text"].split()[0]) + r"\b", u["text"]) and re.search(r"\b(is|are|means|refers to|states)\b", u["text"][:70]):
                score += 0.15
        elif intent == "formula" and kind == "formula":
            score += 0.4
        elif intent == "unit" and kind == "table":
            score += 0.4
        elif intent == "list" and u.get("group"):
            score += 0.4
        elif intent == "law" and kind == "sentence" and re.search(r"\bstates?\b", u["text"]):
            score += 0.2
        if kind == "section":
            score += 0.35 if intent == "overview" else 0
            if intent != "overview":
                score *= 0.55
        elif intent == "overview" and kind in ("definition", "sentence", "table"):
            score *= 0.8
        if kind == "sentence" and u.get("vars") and not symbol_q:
            score *= 0.6
        if kind == "formula" and intent not in ("formula", "unit"):
            score *= 0.8
        need = 0.5 if len(focus) < 3 else 0.4
        if cover < need and not (kt and score >= 0.7):
            continue
        scored.append((score, u))
    scored.sort(key=lambda x: -x[0])
    if not scored:
        return []
    best = scored[0][0]
    return [(u, float(sc)) for sc, u in scored[:k] if sc >= best * 0.55]


def _present(unit):
    kind = unit["kind"]
    if kind == "formula":
        f = unit["formula"]
        return {"answer": f.raw, "tex": f.latex, "extra": "; ".join(f"{s} = {m}" for s, m in f.used_variables), "kind": kind}
    if kind == "definition":
        term, _, mean = unit["text"].partition(": ")
        return {"answer": f"{term} is {mean[0].lower() + mean[1:] if mean[:2].islower() or mean[:1].isupper() and mean[1:2].islower() else mean}", "kind": kind}
    if kind == "table":
        return {"answer": unit["text"], "kind": kind}
    if kind == "section":
        head = "Your notes cover these topics:" if unit.get("overall") else f"Key points of {unit['key']}:"
        return {"answer": head, "items": unit["items"], "kind": kind}
    out = {"answer": unit["text"], "kind": kind}
    g = unit.get("group")
    if g and len(g["items"]) > 1:
        out["answer"] = (g["label"] + ": " if g["label"] else "") + "; ".join(g["items"])
    elif unit.get("formula") is not None:
        f = unit["formula"]
        out["tex"], out["raw"] = f.latex, f.raw
    return out


def present_best(ranked):
    """Present the top unit; if it is a sentence that quotes a formula found among the other hits, show the formula too."""
    best = ranked[0][0]
    shown = _present(best)
    if best["kind"] == "sentence" and "tex" not in shown:
        flat = re.sub(r"\s+", "", best["text"])
        for u, _ in ranked[1:]:
            if u["kind"] == "formula" and re.sub(r"\s+", "", u["formula"].raw) in flat:
                shown["tex"], shown["raw"] = u["formula"].latex, u["formula"].raw
                break
    return best, shown


def _topics(doc, n=4):
    names = [d.term for d in doc.definitions][:n]
    for s in doc.all_sections():
        if len(names) >= n:
            break
        if s.title and s.title not in names:
            names.append(s.title)
    return names[:n]


def get_answers(text, questions):
    """Return [{'question','answer','tex','extra','source','method','support'}] for each question."""
    doc = parse(text)
    units = _units(doc)
    use_model = os.environ.get("QA_BACKEND", "auto").lower() != "search"
    results = []
    for question in questions:
        ranked = _rank(units, question) if units else []
        if not ranked:
            results.append({"question": question, "answer": NO_ANSWER, "method": "search", "kind": "none", "support": [], "hint": _topics(doc)})
            continue
        best, shown = present_best(ranked)
        res = {"question": question, **shown, "source": best["section"], "method": "search",
               "support": [u["text"] for u, _ in ranked[1:]]}
        if use_model and best["kind"] == "sentence":
            try:
                ctx = " ".join(u["text"] for u, _ in ranked)
                out = _pipeline()(question=question, context=ctx, handle_impossible_answer=True)
                if (out.get("answer") or "").strip() and out.get("score", 0) > 0.2:
                    res.update({"answer": out["answer"].strip(), "method": "model", "extra": best["text"]})
            except Exception as exc:
                log.warning("QA model unavailable, using passage search: %s", exc)
                use_model = False
        results.append(res)
    return results