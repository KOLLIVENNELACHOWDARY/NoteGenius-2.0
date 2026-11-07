"""Multiple-choice quizzes from the structure of the notes.

Question types: definitions ("which term is defined as..."), formulas ("which formula gives..."),
symbols ("what does v stand for?"), table lookups, and fill-in-the-blank sentences.
Each question: {question, answer, options, difficulty, context, type, section, tex (option -> LaTeX)}.
"""
import random
import re

from . import formulas as fx
from .nlp import ensure_nltk, stopword_set
from .structure import Document, compress, key_points, parse

DIFFICULTY_MIN_LEN = {"easy": 3, "medium": 4, "hard": 5}
TYPE_ORDER = {
    "easy": ["definition", "formula", "symbol", "table", "cloze"],
    "medium": ["formula", "definition", "table", "symbol", "cloze"],
    "hard": ["cloze", "symbol", "table", "formula", "definition"],
}


def _options(answer, pool, rng, n=4):
    """Answer plus up to n-1 distinct distractors from pool (case-insensitive distinct)."""
    seen = {answer.lower()}
    distractors = []
    pool = list(pool)
    rng.shuffle(pool)
    for cand in pool:
        key = cand.lower()
        if key not in seen and cand.strip():
            seen.add(key)
            distractors.append(cand)
        if len(distractors) >= n - 1:
            break
    if len(distractors) < 2:
        return None
    opts = distractors + [answer]
    rng.shuffle(opts)
    return opts


class MCQGenerator:
    def __init__(self):
        self.rng = random
        self._docs = {}

    # --------------------------------------------------- structured types
    def _definition_qs(self, doc, rng):
        terms = [d.term for d in doc.definitions]
        qs = []
        for d in doc.definitions:
            same = [x.term for x in doc.definitions if x.sid == d.sid and x.term != d.term]
            others = same + [t for t in terms if t not in same and t != d.term]
            opts = _options(d.term, others, rng)
            if opts:
                qs.append({"type": "definition", "question": f"Which term is defined as: “{compress(d.meaning, 30).rstrip('.')}”?",
                           "answer": d.term, "options": opts, "context": f"{d.term}: {d.meaning}", "section": d.section})
        return qs

    def _formula_qs(self, doc, rng):
        qs = []
        pool = [f for f in doc.formulas]
        for f in pool:
            title = f.name or next((m for s, m in f.variables if "=" in f.raw and s == f.raw.split("=")[0].strip()), "")
            if not title:
                continue
            others = [g for g in pool if g is not f and fx.formula_key(g.raw) != fx.formula_key(f.raw)]
            opts = _options(f.raw, [g.raw for g in others], rng)
            if opts:
                tex = {g.raw: g.latex for g in pool if g.raw in opts}
                qs.append({"type": "formula", "question": f"Which formula gives {title}?", "answer": f.raw, "options": opts,
                           "tex": tex, "context": f"{title}: {f.raw}" + (f" (where {', '.join(f'{s} = {m}' for s, m in f.used_variables)})" if f.used_variables else ""),
                           "section": f.section})
        return qs

    def _symbol_qs(self, doc, rng):
        qs = []
        allmeanings = [m for f in doc.formulas for _, m in f.variables]
        for f in doc.formulas:
            for sym, meaning in f.used_variables:
                opts = _options(meaning, [m for m in allmeanings if m != meaning], rng)
                if opts:
                    qs.append({"type": "symbol", "question": f"In the formula  {f.raw}  what does “{sym}” represent?",
                               "answer": meaning, "options": opts, "context": f"{f.raw}, where {sym} = {meaning}",
                               "section": f.section, "question_tex": f.latex})
        return qs

    def _table_qs(self, doc, rng):
        qs = []
        for t in doc.tables:
            if len(t.header) < 2 or len(t.body) < 3:
                continue
            for r in t.body:
                for c in range(1, len(t.header)):
                    ans = r[c].strip()
                    if not ans:
                        continue
                    col = [x[c].strip() for x in t.body if x is not r and x[c].strip()]
                    opts = _options(ans, col, rng)
                    if opts:
                        where = t.caption or t.section
                        qs.append({"type": "table",
                                   "question": f"From the table{(' “' + where + '”') if where else ''}: what is the {t.header[c]} for {t.header[0]} “{r[0]}”?",
                                   "answer": ans, "options": opts, "context": f"{t.header[0]} {r[0]}: " + "; ".join(f"{h} = {v}" for h, v in zip(t.header[1:], r[1:])),
                                   "section": t.section})
        return qs

    # ----------------------------------------------------------- cloze
    def _cloze_qs(self, doc, rng, difficulty):
        ensure_nltk("stopwords")
        stop = stopword_set()
        min_len = DIFFICULTY_MIN_LEN.get(difficulty, 4)
        terms = [d.term for d in doc.definitions]
        sentences = []
        titles = {s.uid: s.title for s in doc.all_sections()}
        for uid, pts in key_points(doc, per_section=4, max_words=30).items():
            sec = titles.get(uid, "")
            for p in pts:
                if len(p.split()) >= 7 and ":" not in p[:40] and not fx.looks_like_equation(p):
                    sentences.append((sec, p.rstrip("…")))
        vocab = {}
        for _, s in sentences:
            for w in re.findall(r"[A-Za-z][A-Za-z\-]{3,}", s):
                if w.lower() not in stop:
                    vocab[w.lower()] = w
        qs = []
        for sec, s in sentences:
            cands = [t for t in terms if re.search(r"\b" + re.escape(t) + r"\b", s, re.I)]
            if not cands:
                words = [w for w in re.findall(r"[A-Za-z][A-Za-z\-]{2,}", s) if w.lower() not in stop and len(w) >= min_len and w.lower() in vocab]
                cands = sorted(words, key=len, reverse=True)[:3]
            if not cands:
                continue
            ans = rng.choice(cands[:2]) if len(cands) > 1 else cands[0]
            question = re.sub(r"\b" + re.escape(ans) + r"\b", "_____", s, count=1, flags=re.I)
            if "_____" not in question:
                continue
            pool = [v for k, v in vocab.items() if k != ans.lower() and abs(len(v) - len(ans)) <= 5 and k not in question.lower()]
            opts = _options(ans, pool, rng)
            if opts:
                qs.append({"type": "cloze", "question": question, "answer": ans, "options": opts, "context": s, "section": sec})
        return qs

    # ----------------------------------------------------------- entry
    def generate_from_document(self, doc, num_questions=5, difficulty="medium", types=None, seed=None):
        rng = random.Random(seed)
        pools = {
            "definition": self._definition_qs(doc, rng), "formula": self._formula_qs(doc, rng),
            "symbol": self._symbol_qs(doc, rng), "table": self._table_qs(doc, rng), "cloze": self._cloze_qs(doc, rng, difficulty),
        }
        order = [t for t in TYPE_ORDER.get(difficulty, TYPE_ORDER["medium"]) if (not types or t in types) and pools[t]]
        for k in pools:
            rng.shuffle(pools[k])
        out, used = [], set()
        while order and len(out) < num_questions:
            for t in list(order):
                if not pools[t]:
                    order.remove(t)
                    continue
                q = pools[t].pop()
                key = q["question"].lower()
                if key in used:
                    continue
                used.add(key)
                q["difficulty"] = difficulty
                q.setdefault("tex", {})
                out.append(q)
                if len(out) >= num_questions:
                    break
        return out

    def generate_mcqs(self, text, num_questions=5, difficulty="medium", types=None):
        return self.generate_from_document(parse(text), num_questions, difficulty, types)

    def available_types(self, text):
        doc = parse(text)
        rng = random.Random(1)
        return {
            "definition": len(self._definition_qs(doc, rng)), "formula": len(self._formula_qs(doc, rng)),
            "symbol": len(self._symbol_qs(doc, rng)), "table": len(self._table_qs(doc, rng)),
        }


def generate_quiz(text, num_questions=5, difficulty="medium"):
    """Convenience wrapper: return a list of question dicts."""
    return MCQGenerator().generate_mcqs(text, num_questions=num_questions, difficulty=difficulty)
