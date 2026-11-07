"""Read an uploaded file (PDF, DOCX, PPTX, TXT/MD, image) into Markdown-like text.

The output keeps structure so the rest of the app can use it:
  # headings, "- " bullets, pipe tables, and formulas ($...$ / $$...$$, or plain "E = mc^2").
"""
import logging
import os
import re
import unicodedata
from collections import Counter

from . import code as codelib
from .boilerplate import is_page_furniture, strip_boilerplate

log = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".txt", ".md", ".png", ".jpg", ".jpeg"}
MAX_PDF_PAGES = 150
MAX_OCR_PAGES = 25
MONO_FONT = re.compile(r"courier|mono|consolas|menlo|monaco|lucida\s?console|inconsolata|source\s?code|fira\s?code|cascadia|"
                       r"andale|typewriter|jetbrains|terminal|couriernew", re.I)
MATHY = re.compile(r"[=±×÷√∑∫∂≤≥≈∞πθ]|\^|_\{")


class ExtractionError(Exception):
    """Raised with a message that is safe to show to the user."""


# ------------------------------------------------------------ normalising
_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
_BULLET_CHARS = "\u2022\uf0b7\uf0a7\uf0d8\uf076\uf0fc\u25cf\u25aa\u25a0\u25e6\u2023\u2043\u00b7"


def normalize_text(text):
    """Fix encoding noise but keep every maths symbol."""
    text = unicodedata.normalize("NFC", text.replace("\r\n", "\n").replace("\r", "\n"))
    for a, b in _LIGATURES.items():
        text = text.replace(a, b)
    text = re.sub("[\u200b\u200c\u200d\u2060\ufeff\u00ad]", "", text).replace("\u00a0", " ").replace("\u2009", " ")
    text = re.sub("^[ \t]*[" + _BULLET_CHARS + "][ \t]*", "- ", text, flags=re.M)
    text = re.sub("[\u201c\u201d]", '"', text)
    text = re.sub("[\u2018\u2019]", "'", text)
    text = re.sub(r"(\w)-\n([a-z])", r"\1\2", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"[ \t]{3,}", "  ", text) if "|" in text and "\t" not in text and False else text
    return re.sub(r"\n{3,}", "\n\n", text).strip()


_JUNK_LINE = re.compile(r"^\s*(?:page\s*)?\d+(?:\s*(?:of|/)\s*\d+)?\s*$|^\s*copyright\b.*$|^\s*all rights reserved.*$", re.I)


def clean_text(text):
    """Normalise and drop page-number / copyright lines (headings such as "Chapter 3" are kept)."""
    text = normalize_text(text)
    lines = [ln for ln in text.split("\n") if not _JUNK_LINE.match(ln)]
    cleaned = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return cleaned or text.strip()


# --------------------------------------------------------------------- OCR
def _ocr(image):
    """OCR a PIL image. Returns '' if Tesseract is not installed."""
    try:
        import pytesseract

        return pytesseract.image_to_string(image)
    except Exception as exc:  # TesseractNotFoundError, missing package, bad image
        log.warning("OCR unavailable or failed: %s", exc)
        return ""


# --------------------------------------------------------------------- PDF
def _line_text(line):
    """Text of a pdfplumber line; marks superscripts/subscripts as ^{} / _{} when the line looks like maths."""
    text = line["text"]
    chars = [c for c in line.get("chars", []) if c.get("text", "").strip()]
    if len(chars) < 3 or not (line.get("merged") or MATHY.search(text)):
        return text
    sizes = sorted(c["size"] for c in chars)
    ms = sizes[len(sizes) // 2]
    big = [c for c in chars if c["size"] >= 0.9 * ms]
    if not big:
        return text
    base = sorted(c["bottom"] for c in big)[len(big) // 2]
    if not any(c["size"] < 0.85 * ms for c in chars) and not line.get("merged"):
        return text
    out, mode, prev = [], None, None
    for c in sorted(line["chars"], key=lambda c: c["x0"]):
        ch = c["text"]
        kind = None
        if ch.strip() and c["size"] < 0.85 * ms:
            kind = "^" if c["bottom"] < base - 0.22 * ms else "_"
        if kind != mode:
            if mode:
                out.append("}")
            if kind:
                out.append(kind + "{")
            mode = kind
        if prev is not None and c["x0"] - prev["x1"] > 0.22 * c["size"] and not mode and ch.strip():
            out.append(" ")
        out.append(ch)
        prev = c
    if mode:
        out.append("}")
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _avg_size(line):
    cs = [c["size"] for c in line.get("chars", []) if c["text"].strip()]
    return sum(cs) / len(cs) if cs else 0


def _merge_scripts(lines):
    """Attach stray sub/superscript fragments ("1", "2" under "x + x") to the line they belong to."""
    hosts = [ln for ln in lines if len(ln["text"].strip()) > 4]
    drop = set()
    for i, ln in enumerate(lines):
        if len(ln["text"].strip()) > 4 or not ln.get("chars"):
            continue
        sz = _avg_size(ln)
        best, best_d = None, 1e9
        for h in hosts:
            hs = _avg_size(h)
            if hs and sz < 0.88 * hs and ln["x0"] >= h["x0"] - 1 and ln["x1"] <= h["x1"] + 1 \
                    and ln["top"] >= h["top"] - 0.7 * hs and ln["bottom"] <= h["bottom"] + 0.7 * hs:
                d = abs(ln["top"] - h["top"])
                if d < best_d:
                    best, best_d = h, d
        if best is not None:
            best["chars"] = list(best["chars"]) + list(ln["chars"])
            best["merged"] = True
            drop.add(i)
    return [ln for i, ln in enumerate(lines) if i not in drop]


def _inside(line, box, pad=3):
    x0, top, x1, bottom = box
    return line["x0"] >= x0 - pad and line["x1"] <= x1 + pad and line["top"] >= top - pad and line["bottom"] <= bottom + pad


def _extract_pdf(path):
    import pdfplumber

    pages = []
    ocr_pages = 0
    sizes = Counter()
    bold_chars = total_chars = 0
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages[:MAX_PDF_PAGES]:
                items = []
                try:
                    tables = page.find_tables()
                except Exception:
                    tables = []
                boxes = [t.bbox for t in tables]
                try:
                    lines = page.extract_text_lines(return_chars=True, strip=True, y_tolerance=5)
                except Exception:
                    lines = []
                lines = _merge_scripts(lines)
                body = [ln for ln in lines if not any(_inside(ln, b) for b in boxes)]
                if sum(len(ln["text"]) for ln in lines) < 20 and ocr_pages < MAX_OCR_PAGES:
                    ocr_pages += 1
                    text = _ocr(page.to_image(resolution=200).original)
                    pages.append({"height": page.height, "items": [{"kind": "raw", "top": 0, "text": text}]})
                    continue
                for ln in body:
                    chars = ln.get("chars", [])
                    if not chars:
                        continue
                    size = sum(c["size"] for c in chars) / len(chars)
                    solid = [c for c in chars if c["text"].strip()]
                    mono = bool(solid) and sum(bool(MONO_FONT.search(c.get("fontname", ""))) for c in solid) >= 0.8 * len(solid)
                    bold = all(re.search(r"bold|black|heavy|semibold", c.get("fontname", ""), re.I) for c in chars if c["text"].strip())
                    for c in chars:
                        if c["text"].strip() and not mono:
                            sizes[round(c["size"], 1)] += 1
                            total_chars += 1
                            bold_chars += bool(re.search(r"bold|black|heavy", c.get("fontname", ""), re.I))
                    cw = (ln["x1"] - ln["x0"]) / max(1, len(ln["text"])) if mono else 0
                    items.append({"kind": "line", "top": ln["top"], "bottom": ln["bottom"], "size": size, "bold": bold,
                                  "text": ln["text"] if mono else _line_text(ln), "x0": ln["x0"], "mono": mono, "cw": cw})
                for t in tables:
                    try:
                        rows = [[re.sub(r"\s+", " ", (c or "")).strip() for c in row] for row in t.extract()]
                    except Exception:
                        continue
                    rows = [r for r in rows if any(r)]
                    if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                        items.append({"kind": "table", "top": t.bbox[1], "rows": rows})
                items.sort(key=lambda it: it["top"])
                pages.append({"height": page.height, "items": items})
    except Exception as exc:
        name = type(exc).__name__
        if "Password" in name or "Encrypted" in name:
            raise ExtractionError("This PDF is password protected. Remove the password and try again.")
        log.warning("PDF read failed: %s", exc)
        raise ExtractionError("That PDF could not be read. It may be damaged.")

    body_size = sizes.most_common(1)[0][0] if sizes else 11
    big_sizes = sorted({s for s in sizes if s >= body_size * 1.12 and sizes[s] < total_chars * 0.25}, reverse=True)
    use_bold = total_chars and bold_chars / total_chars < 0.3

    # running headers / footers, page numbers, college names in the page margins
    def edge_key(it):
        return re.sub(r"\d+", "#", re.sub(r"\s+", " ", it["text"].strip().lower()))

    def edge_items(pg):
        lines = [it for it in pg["items"] if it["kind"] == "line"]
        zone = [it for it in lines if it["top"] < pg["height"] * 0.12 or it["bottom"] > pg["height"] * 0.9]
        ends = lines[:2] + lines[-2:]
        return zone, ends

    zone_repeats, end_repeats = Counter(), Counter()
    for pg in pages:
        zone, ends = edge_items(pg)
        zone_repeats.update({edge_key(it) for it in zone})
        end_repeats.update({edge_key(it) for it in ends})
    npages = len(pages)
    need = 2 if npages >= 2 else 99
    if npages >= 4:
        need = max(2, int(npages * 0.3))
    for pg in pages:
        zone, ends = edge_items(pg)
        kill = set()
        for it in zone:
            k = edge_key(it)
            if is_page_furniture(it["text"]) or (zone_repeats[k] >= need and len(k) > 1):
                kill.add(id(it))
        for it in ends:
            if end_repeats[edge_key(it)] >= need and len(edge_key(it)) > 3 and not it.get("mono"):
                kill.add(id(it))
        pg["items"] = [it for it in pg["items"] if id(it) not in kill]

    out = []
    group = []

    def flush_code():
        if group:
            base = min(g["x0"] for g in group)
            cw = max((g["cw"] for g in group if g["cw"]), default=5) or 5
            out.append("")
            out.append("```")
            out.extend(" " * max(0, round((g["x0"] - base) / cw)) + g["text"].strip() for g in group)
            out.append("```")
            out.append("")
            group.clear()

    for pg in pages:
        prev = None
        for it in pg["items"]:
            if it["kind"] == "raw":
                flush_code()
                out.append(it["text"])
                continue
            if it["kind"] == "table":
                flush_code()
                out.append("")
                out += ["| " + " | ".join(c.replace("|", "/") for c in r) + " |" for r in it["rows"]]
                out.append("")
                prev = None
                continue
            text = it["text"].strip()
            if it.get("mono"):
                group.append(it)
                prev = it
                continue
            flush_code()
            if prev is not None and it["top"] - prev["bottom"] > 0.45 * it["size"]:
                out.append("")
            level = None
            words = text.split()
            if it["size"] >= body_size * 1.12 and len(words) <= 14 and not text.endswith((".", ",", ";")):
                nearest = min(range(len(big_sizes)), key=lambda i: abs(big_sizes[i] - round(it["size"], 1))) if big_sizes else 0
                level = min(nearest + 1, 3)
            elif use_bold and it["bold"] and len(words) <= 10 and len(text) > 2 and not text.endswith((".", ",", ";", ":")) \
                    and not MATHY.search(text):
                level = 3
            if level:
                out.append("")
                out.append("#" * level + " " + text)
                out.append("")
            else:
                out.append(text)
            prev = it
        flush_code()
        out.append("")
    return "\n".join(out)


# -------------------------------------------------------------------- DOCX
_M = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_SKIP = {"rPr", "ctrlPr", "fPr", "dPr", "radPr", "naryPr", "sSupPr", "sSubPr", "sSubSupPr", "funcPr", "limLowPr", "limUppPr",
         "accPr", "barPr", "eqArrPr", "mPr", "argPr", "groupChrPr", "boxPr", "phantPr", "borderBoxPr"}


def _local(el):
    return el.tag.split("}")[-1] if isinstance(el.tag, str) else ""


def _math_symbols(t):
    from .formulas import GREEK, SYMBOLS

    out = []
    for ch in t:
        if ch in GREEK:
            out.append("\\" + GREEK[ch] + " ")
        elif ch in SYMBOLS:
            out.append(SYMBOLS[ch])
        else:
            out.append(ch)
    return "".join(out)


def omml_to_latex(el):
    """Convert a Word equation (OMML element) into LaTeX."""
    tag = _local(el)

    def kids(e):
        return "".join(omml_to_latex(c) for c in e if _local(c) not in _SKIP)

    def part(name):
        node = el.find(_M + name)
        return kids(node) if node is not None else ""

    if tag == "r":
        text = "".join(t.text or "" for t in el.iter(_M + "t"))
        sty = el.find(f"{_M}rPr/{_M}sty")
        text = _math_symbols(text)
        if sty is not None and sty.get(_M + "val") == "p" and re.fullmatch(r"[A-Za-z]{2,}", text.strip()):
            return "\\" + text.strip() + " " if text.strip() in ("sin", "cos", "tan", "log", "ln", "lim", "exp") else "\\mathrm{%s}" % text
        return text
    if tag == "f":
        ftype = el.find(f"{_M}fPr/{_M}type")
        if ftype is not None and ftype.get(_M + "val") == "lin":
            return "{%s}/{%s}" % (part("num"), part("den"))
        return "\\frac{%s}{%s}" % (part("num"), part("den"))
    if tag == "sSup":
        return "{%s}^{%s}" % (part("e"), part("sup"))
    if tag == "sSub":
        return "{%s}_{%s}" % (part("e"), part("sub"))
    if tag == "sSubSup":
        return "{%s}_{%s}^{%s}" % (part("e"), part("sub"), part("sup"))
    if tag == "rad":
        deg = part("deg").strip()
        return "\\sqrt[%s]{%s}" % (deg, part("e")) if deg else "\\sqrt{%s}" % part("e")
    if tag == "nary":
        chr_el = el.find(f"{_M}naryPr/{_M}chr")
        ch = chr_el.get(_M + "val") if chr_el is not None else "∫"
        op = {"∑": "\\sum", "∏": "\\prod", "∫": "\\int", "∬": "\\iint", "∮": "\\oint", "⋃": "\\bigcup", "⋂": "\\bigcap"}.get(ch, "\\int")
        sub, sup = part("sub"), part("sup")
        return op + (("_{%s}" % sub) if sub else "") + (("^{%s}" % sup) if sup else "") + " " + part("e")
    if tag == "d":
        pr = el.find(f"{_M}dPr")
        beg, end = "(", ")"
        if pr is not None:
            b, e = pr.find(_M + "begChr"), pr.find(_M + "endChr")
            beg = b.get(_M + "val") if b is not None else "("
            end = e.get(_M + "val") if e is not None else ")"
        inner = ",".join(kids(e) for e in el.findall(_M + "e"))
        conv = {"{": "\\{", "}": "\\}", "": ".", "|": "|", "‖": "\\|", "⟨": "\\langle", "⟩": "\\rangle", "[": "[", "]": "]"}
        return "\\left%s %s \\right%s" % (conv.get(beg, beg), inner, conv.get(end, end))
    if tag == "func":
        name = part("fName").strip()
        return ("\\" + name + " " if name in ("sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "exp", "lim", "max", "min") else "\\mathrm{%s}" % name) + part("e")
    if tag == "acc":
        chr_el = el.find(f"{_M}accPr/{_M}chr")
        ch = chr_el.get(_M + "val") if chr_el is not None else "̂"
        cmd = {"̂": "\\hat", "̃": "\\tilde", "̄": "\\bar", "⃗": "\\vec", "̇": "\\dot", "̈": "\\ddot"}.get(ch, "\\hat")
        return "%s{%s}" % (cmd, part("e"))
    if tag == "bar":
        return "\\overline{%s}" % part("e")
    if tag == "limLow":
        return "{%s}_{%s}" % (part("e"), part("lim"))
    if tag == "limUpp":
        return "{%s}^{%s}" % (part("e"), part("lim"))
    if tag == "m":
        rows = [" & ".join(kids(e) for e in mr.findall(_M + "e")) for mr in el.findall(_M + "mr")]
        return "\\begin{matrix} " + " \\\\ ".join(rows) + " \\end{matrix}"
    return kids(el)


def _docx_is_mono(para):
    """A Word paragraph set in a code style or a fixed-width font."""
    style = (para.style.name if para.style is not None else "") or ""
    if re.search(r"code|preformatted|verbatim|listing", style, re.I):
        return True
    runs = [r for r in para.runs if r.text.strip()]
    if not runs:
        return False
    return all(MONO_FONT.search(r.font.name or (para.style.font.name if para.style is not None and para.style.font.name else "") or "") for r in runs)


def _docx_paragraph(p):
    parts, display_only = [], True
    for child in p._p.iterchildren():
        name = _local(child)
        if name == "r":
            txt = "".join((t.text or "") if _local(t) == "t" else " " for t in child if _local(t) in ("t", "tab", "br"))
            if txt.strip():
                display_only = False
            parts.append(txt)
        elif name == "hyperlink":
            parts.append("".join(t.text or "" for t in child.iter(_W + "t")))
            display_only = False
        elif name == "oMathPara":
            parts.append(" $$" + " ".join(omml_to_latex(m) for m in child.findall(_M + "oMath")).strip() + "$$ ")
        elif name == "oMath":
            parts.append(" $" + omml_to_latex(child).strip() + "$ ")
    text = "".join(parts)
    return text.strip(), display_only


def _extract_docx(path):
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        doc = Document(path)
    except Exception as exc:
        log.warning("DOCX read failed: %s", exc)
        raise ExtractionError("That Word file could not be read. Save it as .docx and try again.")
    out = []
    code_buf = []

    def flush_code():
        while code_buf and not code_buf[-1].strip():
            code_buf.pop()
        if code_buf:
            out.extend(["", "```"] + code_buf + ["```", ""])
        code_buf.clear()

    for child in doc.element.body.iterchildren():
        name = _local(child)
        if name == "p":
            para = Paragraph(child, doc)
            if _docx_is_mono(para):
                raw = "".join(r.text for r in para.runs).replace("\t", "    ").rstrip()
                if raw.strip():
                    code_buf.append(raw)
                    continue
            if code_buf and not para.text.strip():
                code_buf.append("")  # a blank line inside a program
                continue
            flush_code()
            text, display_only = _docx_paragraph(para)
            if not text:
                out.append("")
                continue
            style = (para.style.name if para.style is not None else "") or ""
            hm = re.match(r"heading\s*(\d)", style, re.I)
            if style.lower() == "title":
                out.append("# " + text)
            elif hm:
                out.append("#" * min(int(hm.group(1)), 4) + " " + text)
            elif "list" in style.lower() or child.find(f"{_W}pPr/{_W}numPr") is not None:
                out.append("- " + text)
            elif display_only and text.startswith("$$"):
                out.append(text)
            else:
                out.append(text)
                out.append("")
        elif name == "tbl":
            flush_code()
            table = Table(child, doc)
            if len(table.rows) == 1 and len(table.columns) == 1:
                cell_text = table.rows[0].cells[0].text.replace("\t", "    ").rstrip()
                cell_lines = cell_text.split("\n")
                cell_mono = all(_docx_is_mono(p) for p in table.rows[0].cells[0].paragraphs if p.text.strip())
                if len(cell_lines) >= 2 and (cell_mono or codelib.find_run(cell_lines, 0)):
                    out.extend(["", "```"] + cell_lines + ["```", ""])
                    continue
            rows = []
            for row in table.rows:
                cells, last = [], None
                for cell in row.cells:
                    if cell._tc is last:
                        continue
                    last = cell._tc
                    cells.append(re.sub(r"\s+", " ", cell.text).strip().replace("|", "/"))
                if any(cells):
                    rows.append(cells)
            if len(rows) >= 1 and max(len(r) for r in rows) >= 2:
                width = max(len(r) for r in rows)
                out.append("")
                out += ["| " + " | ".join(r + [""] * (width - len(r))) + " |" for r in rows]
                out.append("")
            else:
                out += [" ".join(r) for r in rows]
    flush_code()
    return "\n".join(out)


# -------------------------------------------------------------------- PPTX
def _extract_pptx(path):
    from pptx import Presentation

    try:
        prs = Presentation(path)
    except Exception as exc:
        log.warning("PPTX read failed: %s", exc)
        raise ExtractionError("That PowerPoint file could not be read.")
    out = []
    for slide in prs.slides:
        title = slide.shapes.title.text.strip() if slide.shapes.title is not None and slide.shapes.title.has_text_frame else ""
        if title:
            out += ["", "## " + title, ""]
        for shape in slide.shapes:
            if shape == slide.shapes.title:
                continue
            if getattr(shape, "has_table", False) and shape.has_table:
                rows = [[re.sub(r"\s+", " ", c.text).strip().replace("|", "/") for c in r.cells] for r in shape.table.rows]
                out.append("")
                out += ["| " + " | ".join(r) + " |" for r in rows]
                out.append("")
            elif shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    t = "".join(r.text for r in para.runs).strip()
                    if t:
                        out.append("- " + t if shape.is_placeholder else t)
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
            if notes:
                out += ["", notes, ""]
    return "\n".join(out)


# ------------------------------------------------------------------- image
def _extract_image(path):
    from PIL import Image

    try:
        with Image.open(path) as img:
            text = _ocr(img.convert("RGB"))
    except Exception as exc:
        log.warning("Image read failed: %s", exc)
        raise ExtractionError("That image could not be read.")
    if not text.strip():
        raise ExtractionError(
            "No text was found in the image. Photo text recognition may not be installed on this server, "
            "or the photo is too blurry. Handwriting and typeset formulas are not recognised reliably."
        )
    return text


def _read_text_file(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return raw.decode("utf-16")
        except UnicodeError:
            pass
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeError:
            continue
    return raw.decode("latin-1", errors="ignore")


def extract_text_from_file(path, report=None):
    """Extract text from a file on disk, keeping headings, lists, tables and formulas. Raises ExtractionError."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        raw = _extract_pdf(path)
    elif ext == ".docx":
        raw = _extract_docx(path)
    elif ext == ".pptx":
        raw = _extract_pptx(path)
    elif ext in (".png", ".jpg", ".jpeg"):
        raw = _extract_image(path)
    elif ext in (".txt", ".md"):
        raw = _read_text_file(path)
    else:
        raise ExtractionError("Unsupported file type. Use PDF, DOCX, PPTX, TXT, MD, PNG or JPG.")
    cleaned = clean_text(raw) if ext not in (".txt", ".md") else normalize_text(raw)
    if not cleaned.strip():
        raise ExtractionError("No readable text was found in that file.")
    cleaned, removed = strip_boilerplate(cleaned)
    if report is not None:
        report.extend(removed)
    if removed:
        log.info("Ignored %d header / footer / front-page lines", len(removed))
    return cleaned


def extract_with_report(path):
    """(text, ignored_lines): the notes text and the header / footer / cover lines that were left out."""
    report = []
    text = extract_text_from_file(path, report)
    return text, report
