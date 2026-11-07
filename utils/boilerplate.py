"""Drop what is not study content: running headers and footers, page numbers, college / university
names, faculty and student details, cover and certificate pages, tables of contents, watermarks.

Conservative by design. A line is removed only when it clearly looks like boilerplate, and if the pass
would throw away too much of the file it changes nothing. Source code is never touched.

strip_boilerplate(text) -> (clean_text, [removed lines])
is_page_furniture(line)  -> True for lines that are junk when they sit in a page header / footer zone
"""
import re
from collections import defaultdict

from . import code as codelib

# ------------------------------------------------------------ line patterns
_PAGE_NO = re.compile(
    r"^[\-–—\s]*(?:page|pg\.?|p\.)?\s*\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?[\-–—\s]*$"
    r"|^\d{1,4}\s*[|/]\s*(?:page|\d{1,4})\s*$|^page\s*[|:]?\s*\d+(?:\s*(?:of|/)\s*\d+)?\s*$", re.I)

_WATERMARK = re.compile(
    r"^(?:confidential|strictly confidential|for (?:internal|private|college|student) (?:use|circulation|purpose)s?(?: only)?|"
    r"do not (?:copy|distribute|share)\b.*|not for (?:sale|distribution)\b.*|scanned (?:by|with|using)\b.*|camscanner|"
    r"downloaded from\b.*|download(?:ed)? (?:more|free)\b.*|powered by\b.*|created (?:with|by|using)\b.*|generated (?:by|with|using)\b.*|"
    r"(?:join|follow|visit|subscribe)\b.*(?:telegram|whatsapp|youtube|instagram|channel|\.com|\.in|\.org|\.net).*|"
    r"study ?materials?\b.{0,30}|lecture notes?\b.{0,30}|printed (?:on|from)\b.*|©.*|\(c\)\s*\d{4}.*|copyright\b.*|all rights reserved.*|"
    r"(?:https?://|www\.)\S+|\S+@\S+\.\S+|(?:\+?\d{1,3}[\s-]?)?\(?\d{3,5}\)?[\s-]?\d{3,5}[\s-]?\d{3,5})$", re.I)

_STRONG_INST = re.compile(
    r"\b(aicte|naac|nba[\s\-]accredited|ugc|autonomous|affiliated\s+to|approved\s+by|accredited\s+(?:by|with)|estd\.?|established\s+in\s+\d{4}|"
    r"iso\s*\d{4,5}|(?:a\s+)?grade\s+(?:by|accredited)|deemed\s+(?:to\s+be\s+)?university|nirf|an\s+(?:autonomous\s+)?institution|"
    r"(?:jntu[a-z]*|anna|vtu|osmania|mumbai|delhi|pune|calicut|mg|rgpv|gtu|aktu|kuk|mdu)\s+university)\b", re.I)

_WEAK_INST = re.compile(
    r"\b(college|university|institute|institution|academy|vidyalaya|vidyapeeth|polytechnic|school\s+of|faculty\s+of|"
    r"department\s+of|dept\.?\s+of|centre\s+for|center\s+for|campus)\b", re.I)

_META_ANY = re.compile(
    r"^(?:(?:prepared|submitted|presented|compiled|written|handled|guided|reviewed|verified|approved|supervised|taught|delivered)\s+(?:by|to)\b.*|"
    r"under\s+the\s+(?:guidance|supervision)\s+of\b.*|"
    r"(?:name\s+of\s+the\s+(?:faculty|staff|teacher|student|professor|lecturer)|faculty(?:\s+name|\s+incharge|\s+in-charge)?|staff(?:\s+name)?|"
    r"hod|head\s+of\s+(?:the\s+)?department|principal|guide|mentor|instructor|lecturer|professor|"
    r"roll\s*(?:no|number|\.)|reg(?:ister|istration)?\.?\s*(?:no|number)|usn|enrol(?:l)?ment\s*(?:no|number)|employee\s*id|emp\.?\s*id|"
    r"academic\s*year|regulation|subject\s*code|course\s*code|paper\s*code|year\s*/\s*sem(?:ester)?|semester|sem)\s*[:\-–=]\s*\S.*|"
    r"(?:b\.?\s?tech|m\.?\s?tech|b\.?e\.?|m\.?e\.?|b\.?sc|m\.?sc|bca|mca|mba|b\.?com|diploma)\b.{0,40}(?:year|sem(?:ester)?|branch|section).*|"
    r"(?:i|ii|iii|iv|1st|2nd|3rd|4th|first|second|third|final)\s+(?:year|sem(?:ester)?)\b.{0,40}|"
    r"academic\s+year\s+\d{4}.*|\d{4}\s*[-–]\s*(?:\d{4}|\d{2})\s*(?:academic\s+year|batch)?|"
    r"(?:assistant|associate)?\s*professor(?:\s*,.*|\s+(?:in|of)\s+.*)?|"
    r"(?:dr|prof|mr|mrs|ms|er)\.?\s+[A-Z][A-Za-z.\s]{2,40}(?:,\s*[A-Za-z.\s,]{2,40})?)$", re.I)

# generic words that are metadata only in the front or back of a document
_META_EDGE = re.compile(
    r"^(?:name|class|section|branch|batch|date|place|year|department|dept\.?|subject|course|topic|unit|time|venue|roll|id)\s*[:\-–]\s*[^=]{0,70}$", re.I)

_SIGNATURE = re.compile(
    r"^(?:signature(?:\s+of\b.*)?|(?:internal|external)\s+examiner|head\s+of\s+(?:the\s+)?department|principal|hod|project\s+(?:guide|coordinator)|"
    r"guide|place\s*:.*|date\s*:.*|seal|sign(?:ed)?\b.*|\.{4,}|_{4,}|—{3,}|-{5,})$", re.I)

_CERT_START = re.compile(
    r"^(?:this\s+is\s+to\s+certify|certified\s+that|we\s+hereby\s+declare|i\s+hereby\s+declare|i\s+declare\s+that|"
    r"(?:i|we)\s+(?:would\s+like|wish|take\s+this\s+opportunity)\s+to\s+(?:express|thank|convey)|"
    r"(?:i|we)\s+am\s+(?:extremely\s+)?(?:thankful|grateful)|submitted\s+in\s+partial\s+fulfil?l?ment|"
    r"a\s+(?:mini\s+|major\s+)?(?:project|seminar|dissertation|thesis|report|record)\s+(?:report|work)?\s*(?:submitted|on)\b|"
    r"bonafide\b|in\s+partial\s+fulfil?l?ment)", re.I)

_FRONT_HEAD = re.compile(
    r"^(?:#{1,6}\s*)?(?:bonafide\s+)?(certificate|declaration|acknowledg(?:e)?ments?|preface|dedication|abstract\s+page|"
    r"table\s+of\s+contents|contents|list\s+of\s+(?:figures|tables|abbreviations|symbols|illustrations)|"
    r"references|bibliography|further\s+reading|index)\s*:?\s*$", re.I)
_TOC_HEAD = re.compile(r"^(?:#{1,6}\s*)?(table\s+of\s+contents|contents|list\s+of\s+\w+)\s*:?\s*$", re.I)
_TAIL_HEAD = re.compile(r"^(?:#{1,6}\s*)?(references|bibliography|further\s+reading)\s*:?\s*$", re.I)

_TOC_ENTRY = re.compile(r"^.{2,90}?(?:\.{3,}|…+|\s{3,}|\t)\s*[\divxlc]{1,4}\s*$|^.{2,90}?\.{3,}\s*$", re.I)
_DOT_LEADER = re.compile(r"^.{3,90}?(?:\.{4,}|…{2,}|(?:\.\s){4,})\s*[\divxlc]{1,4}\s*$", re.I)

_MD_HEAD = re.compile(r"^\s{0,3}#{1,6}\s+\S")
_NUM_HEAD = re.compile(r"^\d+(?:\.\d+){0,3}[.)]?\s+[A-Z]")
_WORD_HEAD = re.compile(r"^(?:chapter|unit|section|module|topic|lesson|part)\s+[\dIVXivx]+\b", re.I)
_BULLET = re.compile(r"^\s*(?:[-*+•▪●◦‣]|\d{1,2}[.)])\s+")

_SENT_STOP = re.compile(r"\b(the|is|are|was|were|of|that|which|this|and|to|in|for|with|can|will|be|by|as|an|it|has|have)\b", re.I)


def _plain(line):
    t = line.strip()
    t = re.sub(r"^#{1,6}\s*", "", t)
    t = re.sub(r"^[-*+•]\s+", "", t)
    return re.sub(r"\s+", " ", t.strip(" *_|"))


def _words(t):
    return len(t.split())


def _is_sentence(t):
    return _words(t) >= 9 and len(_SENT_STOP.findall(t)) >= 4


def _ends_prose(t):
    return t.endswith((".", "?", "!", ",", ";")) and _words(t) > 4


def _titleish(t):
    letters = [w for w in re.findall(r"[A-Za-z][A-Za-z.&'’\-]*", t) if len(w) > 2]
    if not letters:
        return False
    if t.isupper():
        return True
    caps = sum(1 for w in letters if w[0].isupper())
    return caps / len(letters) >= 0.7


def is_page_furniture(line):
    """Junk when seen in a page header/footer: page numbers, watermarks, contact lines, college and faculty lines."""
    t = _plain(line)
    if not t:
        return False
    if len(t) > 160:
        return False
    if _PAGE_NO.match(t) or _WATERMARK.match(t):
        return True
    if _STRONG_INST.search(t) and not _is_sentence(t):
        return True
    if _META_ANY.match(t) or _META_EDGE.match(t):
        return True
    if _WEAK_INST.search(t) and _words(t) <= 14 and not _is_sentence(t) and not _ends_prose(t):
        return True
    return False


def _norm_key(line):
    t = _plain(line).lower()
    t = re.sub(r"\d+", "#", t)
    return re.sub(r"[\s|•·]+", " ", t).strip()


def _protected(lines):
    """Indices that belong to code, tables or formulas and must never be removed."""
    keep = set()
    n = len(lines)
    i = 0
    while i < n:
        t = lines[i].strip()
        if t.startswith("```") or t.startswith("~~~"):
            fence = t[:3]
            keep.add(i)
            i += 1
            while i < n and not lines[i].strip().startswith(fence):
                keep.add(i)
                i += 1
            if i < n:
                keep.add(i)
            i += 1
            continue
        if t.startswith("|") or t.startswith("$"):
            keep.add(i)
            i += 1
            continue
        run = codelib.find_run(lines, i) if t else None
        if run:
            keep.update(range(i, run[0]))
            i = run[0]
            continue
        i += 1
    return keep


def _is_heading(line):
    t = line.strip()
    return bool(_MD_HEAD.match(line) or _NUM_HEAD.match(t) or _WORD_HEAD.match(t))


def strip_boilerplate(text, max_loss=0.7):
    lines = text.split("\n")
    n = len(lines)
    nonblank = [i for i, ln in enumerate(lines) if ln.strip()]
    if len(nonblank) < 4:
        return text, []
    keep = _protected(lines)
    drop, reasons = set(), {}

    def mark(i, why):
        if i not in keep:
            drop.add(i)
            reasons.setdefault(i, why)

    # where the "front" (cover / title page) ends: the first real paragraph
    front_end = nonblank[min(len(nonblank), 45) - 1]
    for i in nonblank:
        if _words(lines[i]) >= 20 and not _MD_HEAD.match(lines[i]):
            front_end = min(front_end, i)
            break
    back_start = nonblank[max(0, len(nonblank) - 8)]

    # 1. per-line patterns
    for i in nonblank:
        if i in keep:
            continue
        ln = lines[i]
        t = _plain(ln)
        if not t:
            continue
        in_front, in_back = i <= front_end, i >= back_start
        bullet = bool(_BULLET.match(ln)) and not ln.lstrip().startswith("#")
        if _PAGE_NO.match(t) and not bullet:
            mark(i, "page number")
        elif _WATERMARK.match(t) and not bullet and _words(t) <= 14:
            mark(i, "watermark / contact line")
        elif _DOT_LEADER.match(t):
            mark(i, "contents entry")
        elif _STRONG_INST.search(t) and not _is_sentence(t) and _words(t) <= 18 and not bullet:
            mark(i, "institution line")
        elif _META_ANY.match(t) and not bullet and _words(t) <= 14 and (in_front or in_back or re.match(
                r"^(prepared|submitted|presented|compiled|handled|guided|under the|roll|reg|usn|faculty|staff|hod|academic year|subject code|course code|paper code|name of the)", t, re.I)):
            mark(i, "faculty / student details")
        elif _META_EDGE.match(t) and not bullet and (in_front or in_back) and _words(t) <= 10:
            mark(i, "cover details")
        elif _WEAK_INST.search(t) and not bullet and (in_front or in_back) and _words(t) <= 12 and _titleish(t) \
                and not _is_sentence(t) and not _ends_prose(t):
            mark(i, "college / department name")
        elif _SIGNATURE.match(t) and (in_front or in_back) and not bullet:
            mark(i, "signature line")

    # a header line with a page number or separators ("COLLEGE NAME | Unit II | Page 4") anywhere in the file
    for i in nonblank:
        if i in keep or i in drop:
            continue
        t = _plain(lines[i])
        if (_WEAK_INST.search(t) or _STRONG_INST.search(t)) and _words(t) <= 16 and not _is_sentence(t) and not _BULLET.match(lines[i]) \
                and (re.search(r"\||•|·", t) or re.search(r"(?:page|pg\.?|p\.)\s*\d+\s*$|[-–—]\s*\d{1,4}\s*$", t, re.I)):
            mark(i, "running header / footer")
    # the same line elsewhere (only the page number differs) goes too
    gone = {_norm_key(lines[i]) for i in drop if lines[i].strip() and _words(_plain(lines[i])) >= 3}
    if gone:
        for i in nonblank:
            if i not in keep and i not in drop and _norm_key(lines[i]) in gone:
                mark(i, "repeated header / footer")

    # 2. lines that repeat through the document (running headers / footers)
    blocks_of = defaultdict(set)
    seen_lines = defaultdict(list)
    block = 0
    for i, ln in enumerate(lines):
        if not ln.strip():
            block += 1
            continue
        if i in keep or i in drop:
            continue
        t = _plain(ln)
        if _words(t) < 3 and not re.search(r"[|•·©]", t):
            continue
        if t.endswith((".", ":", ";", "?", "!")) or "=" in t or _BULLET.match(ln) or re.match(r"^(fig|figure|table|example|solution)\b", t, re.I):
            continue
        k = _norm_key(ln)
        blocks_of[k].add(block)
        seen_lines[k].append(i)
    for k, idxs in seen_lines.items():
        if len(idxs) >= 3 and len(blocks_of[k]) >= 3 and (not any(_MD_HEAD.match(lines[i]) for i in idxs) or is_page_furniture(lines[idxs[0]])):
            for i in idxs:
                mark(i, "repeated header / footer")

    # 3. front matter sections (certificate, acknowledgement, contents, references ...)
    i = 0
    while i < n:
        ln = lines[i]
        t = _plain(ln)
        if i in keep or not t:
            i += 1
            continue
        if _FRONT_HEAD.match(ln.strip()) and _words(t) <= 5:
            is_tail = bool(_TAIL_HEAD.match(ln.strip()))
            is_toc = bool(_TOC_HEAD.match(ln.strip()))
            if t.lower() == "index" and i > front_end:
                i += 1
                continue
            mark(i, "front / back matter heading")
            j, taken = i + 1, 0
            while j < n:
                lj = lines[j]
                if lj.strip():
                    if j in keep and not lj.strip().startswith("|"):
                        break
                    if is_toc:
                        if _words(lj) >= 14 or (_is_heading(lj) and not _TOC_ENTRY.match(lj.strip()) and _MD_HEAD.match(lj)):
                            break
                    elif is_tail:
                        if _MD_HEAD.match(lj) or _WORD_HEAD.match(lj.strip()):
                            break
                    else:
                        if _is_heading(lj) and _words(lj) <= 8 and not _CERT_START.match(lj.strip()):
                            break
                        if taken >= 40:
                            break
                    taken += 1
                    if j not in keep:
                        mark(j, "front / back matter")
                j += 1
            i = j
            continue
        if _CERT_START.match(t) and i not in drop and (i <= front_end or i >= back_start or _words(t) < 60):
            j = i
            while j < n and lines[j].strip() and j not in keep:
                mark(j, "certificate / acknowledgement text")
                j += 1
            i = j
            continue
        i += 1

    # 4. contents lines left over in a table-of-contents block (page numbers at the end of short lines)
    for i in nonblank:
        if i in keep or i in drop:
            continue
        t = _plain(lines[i])
        if _TOC_ENTRY.match(lines[i].strip()) and i <= front_end and _words(t) <= 12 and not _BULLET.match(lines[i]):
            mark(i, "contents entry")

    removed_nonblank = [i for i in drop if lines[i].strip()]
    if not removed_nonblank:
        return text, []
    out = [ln for i, ln in enumerate(lines) if i not in drop]
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()
    # never leave (almost) nothing: a file that is all cover page keeps its text
    if len(re.findall(r"\w+", cleaned)) < 25 and len(removed_nonblank) > 0.5 * len(nonblank):
        return text, []
    report = [lines[i].strip() for i in sorted(removed_nonblank)]
    return cleaned, report
