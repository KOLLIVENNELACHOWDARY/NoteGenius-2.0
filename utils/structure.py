"""Understand notes: headings, paragraphs, lists, tables, formulas, definitions, examples.

`parse(text)` turns the text produced by utils.extract (Markdown-like) or pasted notes into a
`Document`. Every study tool (summary, slides, flashcards, mind map, quiz...) reads from it, so
formulas and tables are handled the same way everywhere.
"""
import hashlib
import re
from dataclasses import dataclass, field
from functools import lru_cache

from . import code as codelib
from . import formulas as fx
from .nlp import split_sentences, stopword_set

BULLET = re.compile(r"^\s*(?:[-*+•▪●◦‣–]|\d{1,2}[.)]|\(\d{1,2}\)|[a-zA-Z][.)]|\([a-zA-Z]\)|[ivxIVX]{1,4}[.)])\s+(\S.*)$")
MD_HEAD = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$")
NUM_HEAD = re.compile(r"^(\d+(?:\.\d+){0,3})[.)]?\s+([A-Z].{1,80})$")
WORD_HEAD = re.compile(r"^(chapter|unit|section|module|topic|lesson|part)\s+[\dIVXivx]+\b.*$", re.I)
SEP_ROW = re.compile(r"^[\s|:+\-=]+$")
LEAD_IN = re.compile(r"^(however|also|moreover|furthermore|in addition|additionally|thus|hence|therefore|so|then|"
                     r"for example|for instance|in fact|basically|generally|note that)\b[,:]?\s+", re.I)
CUES = {"important", "key", "therefore", "thus", "hence", "defined", "must", "always", "never", "law", "theorem",
        "principle", "rule", "remember", "formula", "means", "called", "known", "states", "equal", "proportional",
        "increase", "decrease", "cause", "result", "because", "significant", "main", "primary", "essential"}
PRONOUNS = {"it", "this", "that", "they", "which", "there", "he", "she", "we", "these", "those", "who", "what", "one"}

_DEF_PATTERNS = [
    re.compile(r"^(?:an?\s+|the\s+)?(?P<term>[A-Za-z][\w'’\-/ ]{1,50}?)\s+(?:is|are)\s+(?:defined as|called|known as|termed)\s+(?P<mean>.{12,})$", re.I),
    re.compile(r"^(?:an?\s+|the\s+)?(?P<term>[A-Za-z][\w'’\-/ ]{1,50}?)\s+(?:means|refers to|denotes|can be defined as|is the (?:study|process|measure|ability|tendency|property) of)\s+(?P<mean>.{8,})$", re.I),
    re.compile(r"^(?:an?\s+|the\s+)?(?P<term>[A-Z][\w'’\-/ ]{1,40}?)\s+(?:is|are)\s+(?P<mean>(?:an?|the)\s+.{12,})$"),
]
_CALLED = re.compile(r"^(?P<mean>.{15,}?)\s+(?:is|are)\s+(?:called|known as|termed|referred to as)\s+(?:an?\s+|the\s+)?(?P<term>[A-Za-z][\w'’\- ]{2,40}?)[.;]?$", re.I)
_COLON = re.compile(r"^(?:\*\*)?(?P<term>[A-Z][\w'’\-/ ]{1,40}?)(?:\*\*)?\s*[:–—-]\s+(?P<mean>[A-Za-z].{14,})$")


# ------------------------------------------------------------------ model
@dataclass
class Formula:
    raw: str
    latex: str
    name: str = ""
    context: str = ""
    variables: list = field(default_factory=list)
    section: str = ""
    sid: int = -1

    @property
    def speech(self):
        return fx.to_speech(self.raw, self.latex)

    @property
    def used_variables(self):
        return used_variables(self.raw, self.variables)


def used_variables(raw, variables):
    toks = set(re.findall(r"(?<![A-Za-z0-9])[A-Za-z\u0370-\u03ff](?:_?\{?[A-Za-z0-9]{1,2}\}?)?(?![A-Za-z])", fx.clean_latex_input(raw)))
    toks |= set(re.findall(r"[A-Za-z]", raw))
    keep = [(sy, me) for sy, me in variables if sy in toks or sy[:1] in toks and len(sy) == 1]
    return keep


@dataclass
class Definition:
    term: str
    meaning: str
    section: str = ""
    sid: int = -1


@dataclass
class Table:
    rows: list
    caption: str = ""
    section: str = ""
    sid: int = -1

    @property
    def header(self):
        return self.rows[0] if self.rows else []

    @property
    def body(self):
        return self.rows[1:]


@dataclass
class Section:
    title: str
    level: int = 1
    blocks: list = field(default_factory=list)
    children: list = field(default_factory=list)
    parent: "Section" = None
    uid: int = -1

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    @property
    def path(self):
        return (self.parent.path + " › " if self.parent and self.parent.title else "") + self.title

    def own(self, kind):
        return [b for b in self.blocks if b["kind"] == kind]

    def text(self):
        parts = []
        for b in self.blocks:
            if b["kind"] in ("para", "note", "example"):
                parts.append(b["text"])
            elif b["kind"] == "list":
                parts.extend(b["items"])
        return " ".join(parts)


@dataclass
class Document:
    title: str
    sections: list
    definitions: list = field(default_factory=list)
    formulas: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    word_count: int = 0

    def all_sections(self):
        for s in self.sections:
            yield from s.walk()

    def defs_in(self, sec):
        return [d for d in self.definitions if d.sid == sec.uid]

    def formulas_in(self, sec):
        return [f for f in self.formulas if f.sid == sec.uid]

    def tables_in(self, sec):
        return [t for t in self.tables if t.sid == sec.uid]

    @property
    def codes(self):
        return [(sec, b) for sec in self.all_sections() for b in sec.own("code")]

    @property
    def lists(self):
        out = []
        for sec in self.all_sections():
            for b in sec.own("list"):
                out.append((sec, b))
        return out

    def stats(self):
        secs = [s for s in self.all_sections() if s.title]
        return {
            "sections": len(secs), "definitions": len(self.definitions), "formulas": len(self.formulas),
            "tables": len(self.tables), "words": self.word_count, "code": len(self.codes),
        }


# ---------------------------------------------------------------- helpers
def clean_inline(t):
    t = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), t)
    t = re.sub(r"(?<!\w)\*(\S[^*]*?)\*(?!\w)", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def compress(sentence, max_words=24):
    """Shorten a long sentence at a clause boundary without inventing words."""
    s = LEAD_IN.sub("", clean_inline(sentence)).strip()
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    words = s.split()
    if len(words) <= max_words:
        return s
    cut = " ".join(words[:max_words])
    m = max(cut.rfind(","), cut.rfind(";"), cut.rfind(" which "), cut.rfind(" that "), cut.rfind(" and "))
    if m > len(cut) * 0.5:
        cut = cut[:m]
    return cut.rstrip(",;: ") + "…"


def first_sentence(text, max_words=35):
    sents = split_sentences(text)
    return compress(sents[0] if sents else text, max_words)


def split_cells(line):
    if "|" in line:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
    elif "\t" in line:
        cells = [c.strip() for c in line.split("\t")]
    else:
        cells = [c.strip() for c in re.split(r"\s{2,}", line.strip())]
    return cells


def _table_candidate(line):
    if not line.strip() or MD_HEAD.match(line):
        return None
    pipes = line.count("|")
    if pipes >= 2 or (pipes == 1 and line.strip().startswith("|")):
        return "pipe"
    if "\t" in line.strip() and len(split_cells(line)) >= 2:
        return "tab"
    cells = split_cells(line)
    if len(cells) >= 2 and all(len(c.split()) <= 6 and len(c) <= 40 for c in cells) and not line.rstrip().endswith((".", ":")):
        return "space"
    return None


def _is_formula_line(line):
    t = line.strip()
    if not t or BULLET.match(line) and not fx.looks_like_equation(BULLET.match(line).group(1)):
        return False
    if t.startswith("$$") or (t.startswith("$") and t.endswith("$")):
        return True
    t = re.sub(r"^(formula|equation|expression|relation)\s*[:\-–]\s*", "", t, flags=re.I)
    t = t.rstrip(" .;")
    nm = re.match(r"^([A-Za-z][\w'’ \-]{2,50}?)\s*:\s*(.+)$", t)
    if nm and "=" not in nm.group(1) and len(nm.group(1).split()) <= 7:
        t = nm.group(2)
    return fx.looks_like_equation(t) and len(t.split()) <= 14


def _heading_level(line, prev_blank, next_line, prev_line=""):
    t = line.strip()
    if not t or len(t) > 85 or BULLET.match(line) or t[-1] in ".,;!?":
        return None
    words = t.split()
    if len(words) > 11 or fx.looks_like_equation(t) or _table_candidate(line) == "pipe":
        return None
    m = NUM_HEAD.match(t)
    if m:
        return min(m.group(1).count(".") + 1, 4)
    if WORD_HEAD.match(t):
        return 1
    if t.isupper() and len(t) > 3 and any(c.isalpha() for c in t):
        return 2
    if t.endswith(":"):
        return None
    # a short capitalised label right under a title or a finished sentence, followed by a real sentence: "Purpose", "Scope"
    if (not prev_blank and len(words) <= 3 and t[0].isupper() and not _DEF_ANY(t) and len(next_line.split()) >= 6
            and (not prev_line.strip() or prev_line.strip()[-1] in ".!?:" or prev_line.strip().isupper() or len(prev_line.split()) <= 8)):
        return 2
    if prev_blank:
        sig = [w for w in words if len(w) > 3]
        caps = sum(1 for w in sig if w[0].isupper())
        if t[0].isupper() and (len(words) <= 4 or (sig and caps / len(sig) >= 0.6)) and not _DEF_ANY(t):
            return 2
    return None


def _DEF_ANY(t):
    return bool(re.search(r"\b(is|are|was|were|means|has|have)\b", t)) and len(t.split()) > 4


# ------------------------------------------------------------------ blocks
def _read_blocks(text):
    lines = text.replace("\r", "").split("\n")
    n = len(lines)
    blocks, para = [], []

    def flush():
        if para:
            blocks.append({"kind": "para", "text": clean_inline(" ".join(para))})
            para.clear()

    i = 0
    prev_blank = True
    while i < n:
        line = lines[i]
        t = line.strip()
        if not t:
            flush()
            prev_blank = True
            i += 1
            continue

        if t.startswith("@@source: "):
            flush()
            blocks.append({"kind": "heading", "level": 0, "text": clean_inline(t[10:])})
            prev_blank = False
            i += 1
            continue

        if t.startswith("```") or t.startswith("~~~"):
            flush()
            fence, lang = t[:3], t[3:].strip().lower()
            buf = []
            i += 1
            while i < n and not lines[i].strip().startswith(fence):
                buf.append(lines[i].rstrip())
                i += 1
            i += 1
            body = "\n".join(buf).strip("\n")
            if body.strip():
                blocks.append({"kind": "code", "lang": lang or codelib.guess_lang(body), "text": body})
            prev_blank = False
            continue

        run = codelib.find_run(lines, i)
        if run:
            flush()
            end, body = run
            blocks.append({"kind": "code", "lang": codelib.guess_lang(body), "text": body})
            prev_blank = False
            i = end
            continue

        m = MD_HEAD.match(line)
        if m:
            flush()
            blocks.append({"kind": "heading", "level": len(m.group(1)), "text": clean_inline(m.group(2))})
            prev_blank = False
            i += 1
            continue

        if t.startswith("$$"):
            flush()
            body = t[2:]
            if body.endswith("$$") and len(body) > 2:
                tex = body[:-2]
            else:
                buf = [body] if body else []
                i += 1
                while i < n and "$$" not in lines[i]:
                    buf.append(lines[i])
                    i += 1
                if i < n:
                    buf.append(lines[i].split("$$")[0])
                tex = " ".join(buf)
            blocks.append({"kind": "formula", "raw": tex.strip(), "latex": fx.to_latex(tex), "name": ""})
            prev_blank = False
            i += 1
            continue

        kind = _table_candidate(line)
        if kind:
            j, rows = i, []
            while j < n and _table_candidate(lines[j]) == kind:
                rows.append(lines[j])
                j += 1
            ok = len(rows) >= 2 if kind != "space" else len(rows) >= 3
            if ok:
                flush()
                has_sep = any(SEP_ROW.match(r) for r in rows)
                parsed = [split_cells(r) for r in rows if not SEP_ROW.match(r)]
                width = max(len(r) for r in parsed)
                if width >= 2 and (kind != "space" or sum(len(r) == width for r in parsed) >= len(parsed) * 0.8):
                    parsed = [r + [""] * (width - len(r)) for r in parsed]
                    caption = ""
                    if blocks and blocks[-1]["kind"] == "para" and re.match(r"^table\b", blocks[-1]["text"], re.I) and len(blocks[-1]["text"]) < 120:
                        caption = blocks.pop()["text"]
                    blocks.append({"kind": "table", "rows": parsed, "caption": caption, "header": has_sep or True})
                    prev_blank = False
                    i = j
                    continue

        nh = NUM_HEAD.match(t)
        if nh and not para and prev_blank and len(t.split()) <= 11 and t[-1] not in ".,;:!?" and not fx.looks_like_equation(t):
            following = lines[i + 1] if i + 1 < n else ""
            if not (following.strip() and BULLET.match(following) and not nh.group(1).count(".")):
                flush()
                blocks.append({"kind": "heading", "level": min(nh.group(1).count(".") + 1, 4), "text": clean_inline(nh.group(2))})
                prev_blank = False
                i += 1
                continue

        bm = BULLET.match(line)
        if bm and not (fx.looks_like_equation(t) and not re.match(r"^\s*[-*+•]", line)):
            flush()
            items = []
            indent = len(line) - len(line.lstrip())
            while i < n and lines[i].strip():
                bm = BULLET.match(lines[i])
                if bm:
                    items.append(clean_inline(bm.group(1)))
                elif items and (len(lines[i]) - len(lines[i].lstrip())) > indent or (items and not _is_formula_line(lines[i]) and not MD_HEAD.match(lines[i]) and lines[i].strip()[0].islower()):
                    items[-1] = clean_inline(items[-1] + " " + lines[i].strip())
                else:
                    break
                i += 1
            label = ""
            if blocks and blocks[-1]["kind"] == "para" and blocks[-1]["text"].endswith(":") and len(blocks[-1]["text"].split()) <= 14:
                label = blocks.pop()["text"].rstrip(":")
            blocks.append({"kind": "list", "items": items, "label": label})
            prev_blank = False
            continue

        if _is_formula_line(line):
            flush()
            body = re.sub(r"^(formula|equation|expression|relation)\s*[:\-–]\s*", "", t, flags=re.I).rstrip(" .;")
            name = ""
            nm = re.match(r"^([A-Za-z][\w'’ \-]{2,50}?)\s*:\s*(.+)$", body)
            if nm and "=" not in nm.group(1) and len(nm.group(1).split()) <= 7 and fx.looks_like_equation(nm.group(2)):
                name, body = nm.group(1).strip(), nm.group(2).strip()
            raw = body.strip("$ ")
            blocks.append({"kind": "formula", "raw": raw, "latex": fx.to_latex(raw), "name": name})
            prev_blank = False
            i += 1
            continue

        nxt = lines[i + 1] if i + 1 < n else ""
        lvl = _heading_level(line, prev_blank and not para, nxt, lines[i - 1] if i else "")
        if lvl and not para:
            blocks.append({"kind": "heading", "level": lvl, "text": clean_inline(t.rstrip(":"))})
            prev_blank = False
            i += 1
            continue

        em = re.match(r"^(example|e\.g\.|eg|solved example|illustration)\b\s*[\d.:)\-–]*\s*(.*)$", t, re.I)
        nt = re.match(r"^(note|important|remember|tip|key point|key idea|caution)\s*[:\-–]\s*(.+)$", t, re.I)
        if em and not para:
            flush()
            blocks.append({"kind": "example", "text": clean_inline(em.group(2) or t)})
        elif nt and not para:
            flush()
            blocks.append({"kind": "note", "text": clean_inline(nt.group(2))})
        else:
            para.append(t)
        prev_blank = False
        i += 1
    flush()
    return blocks


def _build_tree(blocks, fallback_title):
    root = Section("", 0)
    stack = [root]
    levels = sorted({b["level"] for b in blocks if b["kind"] == "heading"})
    remap = {lv: idx + 1 for idx, lv in enumerate(levels)}
    for b in blocks:
        if b["kind"] == "heading":
            level = remap[b["level"]]
            while stack[-1].level >= level:
                stack.pop()
            sec = Section(b["text"], level, parent=stack[-1] if stack[-1].level else None)
            (stack[-1].children if stack[-1].level else root.children).append(sec)
            stack.append(sec)
        else:
            stack[-1].blocks.append(b)
    sections = root.children
    intro = Section("Overview", 1) if root.blocks else None
    if intro:
        intro.blocks = root.blocks
        sections.insert(0, intro)
    title = fallback_title
    if sections and sections[0].title and not sections[0].blocks and not sections[0].children and len(sections) > 1:
        title = sections.pop(0).title
    if len(sections) == 1 and sections[0].children and len(sections[0].blocks) <= 2 and sections[0].title:
        title = sections[0].title
        sections = sections[0].children
        for s in sections:
            s.parent = None
            for d in s.walk():
                d.level = max(1, d.level - 1)
    if not sections:
        sections = [Section(title, 1)]
    return title, sections


def _split_def(sentence):
    s = clean_inline(sentence).strip().rstrip(".")
    m = _CALLED.match(s)
    if m:
        term, mean = m.group("term"), m.group("mean")
    else:
        term = mean = None
        for pat in [_COLON] + _DEF_PATTERNS:
            m = pat.match(s)
            if m:
                term, mean = m.group("term"), m.group("mean")
                break
    if not term:
        return None
    term = re.sub(r"^(an?|the)\s+", "", term.strip(), flags=re.I).strip(" :-–—")
    words = term.split()
    if not words or len(words) > 6 or words[0].lower() in PRONOUNS or term.lower() in PRONOUNS:
        return None
    if re.search(r"\b(is|are|was|were|has|have|can|will|does|do)\b", term, re.I) or len(mean.split()) < 4:
        return None
    if fx.looks_like_equation(term) or re.search(r"\d", term) and len(words) > 3:
        return None
    return term[0].upper() + term[1:] if term.islower() else term, mean.strip().rstrip(".") + "."


_NAME_DROP = {"the", "a", "an", "by", "using", "is", "are", "given", "called", "known", "as", "with", "use", "from", "and"}


def name_from_sentence(sent):
    """"The solutions are given by the quadratic formula:" -> "Quadratic formula"."""
    last = sent.strip().rstrip(":. ")
    m = re.search(r"(?:formula|equation|expression|law|relation|rule)\s+(?:for|of)\s+(?:the\s+)?(.{3,50})$", last, re.I)
    if m:
        return m.group(1).strip()
    m = re.search(r"((?:[A-Za-z'’\-]+\s+){0,3}(?:formula|equation|identity|theorem|law|principle|rule|progression))$", last, re.I)
    if m:
        toks = m.group(1).split()
        while toks and toks[0].lower() in _NAME_DROP:
            toks.pop(0)
        name = " ".join(toks)
        if name and name.lower() not in ("formula", "equation", "identity", "law", "rule"):
            return name[0].upper() + name[1:]
    return last if len(last.split()) <= 4 and last else ""


def _guess_name(blocks, idx, section):
    """Name for a formula from the sentence/heading just before it."""
    b = blocks[idx]
    if b.get("name"):
        return b["name"]
    if idx > 0:
        prev = blocks[idx - 1]
        if prev["kind"] == "para":
            sents = split_sentences(prev["text"])
            if sents:
                return name_from_sentence(sents[-1])
        if prev["kind"] == "heading":
            return prev["text"]
    return ""


def _collect(doc_sections, doc):
    seen_f, seen_d = set(), set()
    for sec in doc_sections:
        blocks = sec.blocks
        for idx, b in enumerate(blocks):
            if b["kind"] == "formula":
                key = fx.formula_key(b["raw"])
                if key in seen_f:
                    continue
                seen_f.add(key)
                variables, ctx = [], ""
                for nb in blocks[idx + 1: idx + 3]:
                    if nb["kind"] == "para" and re.match(r"^(where|here|given|symbols?|notation|with)\b", nb["text"], re.I):
                        variables = fx.parse_variables(nb["text"])
                        ctx = nb["text"]
                        break
                    if nb["kind"] == "list":
                        vs = [v for it in nb["items"] for v in fx.parse_variables(it)]
                        if len(vs) >= max(1, len(nb["items"]) // 2):
                            variables = vs
                            break
                doc.formulas.append(Formula(b["raw"], b["latex"], _guess_name(blocks, idx, sec), ctx, variables, sec.title, sec.uid))
                if variables:
                    k = idx - 1
                    j = len(doc.formulas) - 2
                    while k >= 0 and blocks[k]["kind"] == "formula" and j >= 0 and doc.formulas[j].sid == sec.uid:
                        if not doc.formulas[j].variables:
                            doc.formulas[j].variables, doc.formulas[j].context = list(variables), ctx
                        k -= 1
                        j -= 1
            elif b["kind"] in ("para", "note", "example"):
                for sent in split_sentences(b["text"]):
                    if re.match(r"^(where|here|given|let|symbols?|notation|with)\b", sent, re.I):
                        continue
                    for raw in fx.find_inline_formulas(sent):
                        key = fx.formula_key(raw)
                        if key in seen_f:
                            continue
                        seen_f.add(key)
                        m = re.search(r"\b(?:where|here)\b(.+)$", sent)
                        variables = fx.parse_variables(m.group(1)) if m else []
                        name = ""
                        nm = re.search(r"([A-Z][\w'’\-]*(?:\s+[A-Za-z][\w'’\-]*){0,2}?\s+(?:law|theorem|equation|formula|principle|identity|rule))\b", sent)
                        if nm and not re.match(r"^(An?|The)\s+\w+\s+(equation|formula)$", nm.group(1)):
                            name = nm.group(1).strip()
                        name = re.sub(r"^(The|An?)\s+", "", name)
                        name = name[:1].upper() + name[1:]
                        if not name:
                            pos = sent.find(raw)
                            prefix = re.sub(r"^(the|a|an)\s+", "", sent[:pos].strip(" ,:-"), flags=re.I)
                            if prefix and len(prefix.split()) <= 4 and prefix.lower() not in ("relation", "formula", "equation", "expression") \
                                    and not re.search(r"\b(is|are|states|gives|where|that)\b", prefix, re.I):
                                name = prefix[0].upper() + prefix[1:]
                        doc.formulas.append(Formula(raw, fx.to_latex(raw), name, sent, variables, sec.title, sec.uid))
        units = []
        for b in blocks:
            if b["kind"] == "para":
                units += split_sentences(b["text"])
            elif b["kind"] == "list":
                units += b["items"]
            elif b["kind"] in ("note",):
                units.append(b["text"])
        for u in units:
            if fx.looks_like_equation(u) and "=" in u and len(u.split()) <= 8:
                continue
            d = _split_def(u)
            if d and d[0].lower() not in seen_d:
                seen_d.add(d[0].lower())
                doc.definitions.append(Definition(d[0], d[1], sec.title, sec.uid))
        for b in blocks:
            if b["kind"] == "table":
                doc.tables.append(Table(b["rows"], b.get("caption", ""), sec.title, sec.uid))


@lru_cache(maxsize=16)
def _parse_cached(digest, text):
    blocks = _read_blocks(text)
    first = next((b["text"] for b in blocks if b["kind"] in ("para", "list")), "")
    fallback = "Study notes"
    title, sections = _build_tree(blocks, fallback)
    doc = Document(title, sections)
    for i, s in enumerate(doc.all_sections()):
        s.uid = i
    _collect(list(doc.all_sections()), doc)
    doc.word_count = len(re.findall(r"\w+", text))
    return doc


def parse(text):
    """Parse notes into a Document (cached; treat the result as read-only)."""
    return _parse_cached(hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest(), text)


# ----------------------------------------------------------- key points
def _sentence_scores(doc):
    stop = stopword_set()
    words = {}
    allsents = []
    for sec in doc.all_sections():
        for b in sec.blocks:
            if b["kind"] in ("para", "note"):
                for s in split_sentences(b["text"]):
                    allsents.append((sec, s))
    for _, s in allsents:
        for w in re.findall(r"[a-z]{3,}", s.lower()):
            if w not in stop:
                words[w] = words.get(w, 0) + 1
    top = max(words.values()) if words else 1
    scored = {}
    for sec, s in allsents:
        toks = re.findall(r"[A-Za-z']+", s)
        if not 6 <= len(toks) <= 60 or fx.looks_like_equation(s) or s.rstrip().endswith(":") \
                or re.match(r"^(where|here|given|let|symbols?|notation)\b", s, re.I):
            continue
        low = [t.lower() for t in toks]
        base = sum(words.get(t, 0) / top for t in low if t not in stop) / (len(toks) ** 0.55)
        cue = sum(1 for t in low if t in CUES) * 0.25
        num = 0.15 if re.search(r"\d", s) else 0
        scored[s] = base + cue + num
    return allsents, scored


def key_points(doc, per_section=4, max_words=26):
    """{section uid: [point, ...]}: author's own bullet items first, then the best-scoring sentences."""
    allsents, scored = _sentence_scores(doc)
    defined = {d.meaning.lower().rstrip(".")[:40] for d in doc.definitions}
    out = {}
    for sec in doc.all_sections():
        pts = []
        for b in sec.own("list"):
            items = [it for it in b["items"] if not fx.looks_like_equation(it)]
            if len(items) >= 2 and all(len(it.split()) <= 5 for it in items):
                pts.append(((b["label"] + ": ") if b["label"] else "Key items: ") + "; ".join(items))
            else:
                pts.extend(compress(it, max_words) for it in items if len(it.split()) >= 2)
        for b in sec.own("note"):
            pts.append(compress(b["text"], max_words))
        sents = [(i, s) for i, (sc, s) in enumerate(allsents) if sc is sec and s in scored]
        sents.sort(key=lambda t: -scored[t[1]])
        picked = []
        for i, s in sents:
            if len(pts) + len(picked) >= per_section + (3 if pts else 0):
                break
            if any(s.lower().startswith(m) or m in s.lower() for m in defined if len(m) > 15):
                continue
            picked.append((i, s))
        for i, s in sorted(picked):
            pts.append(compress(s, max_words))
        seen, uniq = set(), []
        raws = [f.raw for f in doc.formulas if f.sid == sec.uid]
        for p in pts:
            k = p.lower()[:50]
            if any(m in p.lower() for m in defined if len(m) > 15):
                continue
            if len(p.split()) <= 10 and any(r in p for r in raws):
                continue
            if k not in seen:
                seen.add(k)
                uniq.append(p)
        out[sec.uid] = uniq[: per_section + 4]
    return out


def top_sentences(doc, n=6, max_words=30):
    _, scored = _sentence_scores(doc)
    best = sorted(scored, key=lambda s: -scored[s])[: n * 2]
    return [compress(s, max_words) for s in best[:n]]


def reading_minutes(doc):
    return max(1, round(doc.word_count / 200 + len(doc.formulas) * 0.5 + len(doc.tables) * 1))