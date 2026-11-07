"""Designed PowerPoint decks from notes.

Slides: title, outline, then for each section its key points, definitions, formulas (typeset as images,
with a symbol legend), tables (native PowerPoint tables), notes/examples; then a formula sheet,
key takeaways and a quick self-check. Speaker notes carry the source text.
"""
import math
import os
import re
import uuid

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

from . import formulas as fx
from .ques_gen import process_document
from .structure import Document, compress, key_points, parse, top_sentences

NAVY, TEAL, AMBER = "12263F", "0F6B6B", "F2A541"
INK, MUTED, PAPER, LINE = "1B2A41", "5B677A", "F5F7FA", "D8DEE8"
TINT_TEAL, TINT_AMBER = "E3F2F1", "FDF1DC"
SERIF, SANS = "Georgia", "Calibri"
W, H = 13.333, 7.5
MAX_SLIDES = 70


def rgb(h):
    return RGBColor.from_string(h)


def _est_lines(text, width_in, pt):
    cpl = max(8, int(width_in * 72 / (pt * 0.5)))
    return sum(max(1, math.ceil(len(par) / cpl)) for par in text.split("\n"))


def fit_pt(texts, width_in, height_in, max_pt=24, min_pt=11, spacing=1.25):
    """Largest font size at which all texts fit the box (rough estimate)."""
    for pt in range(max_pt, min_pt - 1, -1):
        total = sum(_est_lines(t, width_in, pt) for t in texts) * pt * spacing / 72 + 0.12 * len(texts)
        if total <= height_in:
            return pt
    return min_pt


class Deck:
    def __init__(self, title, footer_label):
        self.prs = Presentation()
        self.prs.slide_width, self.prs.slide_height = Inches(W), Inches(H)
        self.blank = self.prs.slide_layouts[6]
        self.title = title
        self.footer_label = footer_label
        self.n = 0

    # ---------------------------------------------------------- primitives
    def rect(self, slide, x, y, w, h, fill, line=None, shape=MSO_SHAPE.RECTANGLE, radius=None):
        shp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
        shp.fill.solid()
        shp.fill.fore_color.rgb = rgb(fill)
        if line:
            shp.line.color.rgb = rgb(line)
            shp.line.width = Pt(1)
        else:
            shp.line.fill.background()
        shp.shadow.inherit = False
        if radius is not None and shape == MSO_SHAPE.ROUNDED_RECTANGLE:
            shp.adjustments[0] = radius
        return shp

    def text(self, slide, x, y, w, h, paras, pt=18, color=INK, bold=False, font=SANS, align=PP_ALIGN.LEFT,
             anchor=MSO_ANCHOR.TOP, line_spacing=1.1):
        """paras: str or list of str / list of runs [(text, {bold,color,pt,font})]."""
        box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = anchor
        tf.margin_left = tf.margin_right = Inches(0.05)
        tf.margin_top = tf.margin_bottom = Inches(0.03)
        if isinstance(paras, str):
            paras = [paras]
        for i, p in enumerate(paras):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            para.alignment = align
            para.line_spacing = line_spacing
            runs = p if isinstance(p, list) else [(p, {})]
            for t, o in runs:
                r = para.add_run()
                r.text = t
                f = r.font
                f.name = o.get("font", font)
                f.size = Pt(o.get("pt", pt))
                f.bold = o.get("bold", bold)
                f.italic = o.get("italic", False)
                f.color.rgb = rgb(o.get("color", color))
            if i < len(paras) - 1:
                para.space_after = Pt(o.get("gap", 6) if runs else 6)
        return box

    def picture(self, slide, path, x, y, w, h, align="center"):
        """Place an image inside a box, keeping its aspect ratio."""
        from PIL import Image

        with Image.open(path) as im:
            iw, ih = im.size
        scale = min(w / (iw / 300), h / (ih / 300), 1.0 * (w / (iw / 300)))
        pw, ph = iw / iw * min(w, h * iw / ih), 0
        pw = min(w, h * iw / ih)
        ph = pw * ih / iw
        px = x + (w - pw) / 2 if align == "center" else x
        py = y + (h - ph) / 2
        return slide.shapes.add_picture(path, Inches(px), Inches(py), Inches(pw), Inches(ph))

    def notes(self, slide, text):
        if text:
            slide.notes_slide.notes_text_frame.text = text[:2500]

    # -------------------------------------------------------------- chrome
    def content_slide(self, title, label="", notes=""):
        s = self.prs.slides.add_slide(self.blank)
        self.n += 1
        self.rect(s, 0, 0, W, H, "FFFFFF")
        self.rect(s, 0, 0, 0.22, H, TEAL)
        if label:
            self.text(s, 0.65, 0.28, 9, 0.3, label.upper(), pt=11, color=TEAL, bold=True)
        pt = 30 if len(title) <= 42 else 26 if len(title) <= 60 else 22
        self.text(s, 0.65, 0.55, W - 1.3, 0.8, title, pt=pt, color=NAVY, bold=True, font=SERIF, anchor=MSO_ANCHOR.MIDDLE)
        self.rect(s, 0.7, 1.4, 1.1, 0.05, AMBER)
        self.rect(s, 0.7, H - 0.5, W - 1.4, 0.01, LINE)
        self.text(s, 0.65, H - 0.45, 9, 0.3, f"NoteGenius  ·  {self.footer_label}", pt=10, color=MUTED)
        self.text(s, W - 1.5, H - 0.45, 0.85, 0.3, str(self.n), pt=10, color=MUTED, align=PP_ALIGN.RIGHT)
        self.notes(s, notes)
        return s

    # -------------------------------------------------------------- slides
    def title_slide(self, title, subtitle, chips):
        s = self.prs.slides.add_slide(self.blank)
        self.n += 1
        self.rect(s, 0, 0, W, H, NAVY)
        self.rect(s, 0.8, 2.35, 0.12, 2.2, AMBER)
        pt = 46 if len(title) <= 28 else 38 if len(title) <= 48 else 30
        self.text(s, 1.15, 2.2, 10.8, 1.7, title, pt=pt, color="FFFFFF", bold=True, font=SERIF, anchor=MSO_ANCHOR.MIDDLE)
        self.text(s, 1.15, 3.95, 10.8, 0.6, subtitle, pt=20, color="BFD7DA")
        x = 1.15
        for chip in chips:
            w = 0.35 + 0.115 * len(chip)
            self.rect(s, x, 5.1, w, 0.45, "1E3A5C", shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
            self.text(s, x, 5.1, w, 0.45, chip, pt=13, color="FFFFFF", align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
            x += w + 0.2
        self.text(s, 1.15, H - 0.8, 8, 0.4, "Made with NoteGenius", pt=11, color="8FA8B8")
        return s

    def outline_slide(self, items):
        s = self.content_slide("What this deck covers", "Outline")
        cols = 2 if len(items) > 5 else 1
        per = math.ceil(len(items) / cols)
        for c in range(cols):
            chunk = items[c * per:(c + 1) * per]
            for i, name in enumerate(chunk):
                idx = c * per + i + 1
                y = 1.9 + i * 0.78
                x = 0.8 + c * 6.1
                self.rect(s, x, y, 0.5, 0.5, TEAL, shape=MSO_SHAPE.OVAL)
                self.text(s, x, y, 0.5, 0.5, str(idx), pt=16, color="FFFFFF", bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
                self.text(s, x + 0.65, y - 0.02, 5.2, 0.56, name, pt=fit_pt([name], 5.2, 0.54, 20, 13), color=INK, anchor=MSO_ANCHOR.MIDDLE)
        return s

    def bullets_slide(self, title, label, points, notes="", cont=False):
        s = self.content_slide(title + (" (continued)" if cont else ""), label, notes)
        area_w, area_h = W - 1.9, H - 2.35
        flat = [p if isinstance(p, str) else f"{p[0]} — {p[1]}" for p in points]
        pt = fit_pt(flat, area_w - 0.6, area_h - 0.2 * len(points), 24, 14)
        y = 1.75
        for p, plain in zip(points, flat):
            lines = _est_lines(plain, area_w - 0.6, pt)
            h = max(0.5, lines * pt * 1.25 / 72 + 0.12)
            self.rect(s, 0.85, y + 0.12, 0.14, 0.14, TEAL if not isinstance(p, str) else AMBER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.3)
            runs = [(p, {})] if isinstance(p, str) else [(p[0], {"bold": True, "color": TEAL}), (" — " + p[1], {})]
            self.text(s, 1.15, y, area_w - 0.3, h, [runs], pt=pt, color=INK)
            y += h + 0.16
        return s

    def definitions_slide(self, title, label, defs, notes=""):
        s = self.content_slide(title, label, notes)
        n = len(defs)
        cols = 1 if n == 1 else 2
        rows = math.ceil(n / cols)
        cw, ch = (W - 1.9 - (cols - 1) * 0.3) / cols, (H - 2.3 - (rows - 1) * 0.3) / rows
        ch = min(ch, 2.2)
        for i, d in enumerate(defs):
            x, y = 0.85 + (i % cols) * (cw + 0.3), 1.75 + (i // cols) * (ch + 0.3)
            self.rect(s, x, y, cw, ch, TINT_TEAL, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.06)
            self.rect(s, x, y + 0.1, 0.09, ch - 0.2, TEAL)
            self.text(s, x + 0.25, y + 0.1, cw - 0.4, 0.5, d.term, pt=20 if len(d.term) < 26 else 16, color=TEAL, bold=True, font=SERIF)
            meaning = compress(d.meaning, 34)
            self.text(s, x + 0.25, y + 0.62, cw - 0.4, ch - 0.7, meaning, pt=fit_pt([meaning], cw - 0.5, ch - 0.75, 18, 12), color=INK)
        return s

    def formulas_slide(self, title, label, formulas, tmp_dir, notes=""):
        s = self.content_slide(title, label, notes)
        n = len(formulas)
        ch = min(2.55, (H - 2.3 - (n - 1) * 0.25) / n)
        for i, f in enumerate(formulas):
            y = 1.75 + i * (ch + 0.25)
            self.rect(s, 0.85, y, W - 1.9, ch, PAPER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
            self.rect(s, 0.85, y + 0.1, 0.09, ch - 0.2, AMBER)
            used = f.used_variables
            left_w = 6.6 if used else W - 2.5
            if f.name:
                self.text(s, 1.15, y + 0.08, left_w, 0.4, f.name, pt=16, color=TEAL, bold=True)
            img = fx.render_png(f.latex, tmp_dir, fontsize=34, color=NAVY) if f.latex else None
            top = y + (0.5 if f.name else 0.15)
            if img:
                self.picture(s, img[0], 1.15, top + 0.05, left_w - 0.3, ch - (0.85 if f.name else 0.45))
            else:
                self.text(s, 1.15, top, left_w - 0.3, ch - 0.6, f.raw, pt=26, color=NAVY, font="Cambria Math", anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.CENTER)
            if used:
                lines = [[(sym + "  ", {"bold": True, "color": TEAL, "font": "Cambria Math"}), (meaning, {})] for sym, meaning in used[:6]]
                texts = [sym + " " + m for sym, m in used[:6]]
                self.text(s, 7.85, y + 0.12, W - 8.9, ch - 0.2, lines, pt=fit_pt(texts, W - 9.0, ch - 0.25, 16, 11), color=INK, anchor=MSO_ANCHOR.MIDDLE)
        return s

    def table_slide(self, title, label, rows, caption="", cont=False):
        s = self.content_slide(title + (" (continued)" if cont else ""), label)
        ncols = len(rows[0])
        nrows = len(rows)
        y = 1.75
        if caption:
            self.text(s, 0.85, y - 0.1, W - 1.9, 0.4, caption, pt=14, color=MUTED)
            y += 0.4
        width = W - 1.9
        weights = [max(len(r[c]) for r in rows) for c in range(ncols)]
        weights = [min(max(w, 5), 40) for w in weights]
        total = sum(weights)
        col_w = [width * w / total for w in weights]
        pt = 20 if ncols <= 3 and nrows <= 6 else 16 if ncols <= 4 and nrows <= 9 else 13 if ncols <= 6 else 11
        row_h = min(0.75, (H - y - 0.9) / nrows)
        gf = s.shapes.add_table(nrows, ncols, Inches(0.85), Inches(y), Inches(width), Inches(row_h * nrows))
        tbl = gf.table
        tbl.first_row = True
        for c, cw in enumerate(col_w):
            tbl.columns[c].width = Inches(cw)
        for r, row in enumerate(rows):
            tbl.rows[r].height = Inches(row_h)
            for c in range(ncols):
                cell = tbl.cell(r, c)
                cell.margin_left = cell.margin_right = Inches(0.1)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                cell.fill.solid()
                cell.fill.fore_color.rgb = rgb(NAVY if r == 0 else ("FFFFFF" if r % 2 else PAPER))
                tf = cell.text_frame
                tf.word_wrap = True
                tf.text = ""
                run = tf.paragraphs[0].add_run()
                run.text = row[c]
                run.font.size = Pt(pt)
                run.font.name = SANS
                run.font.bold = r == 0 or c == 0
                run.font.color.rgb = rgb("FFFFFF" if r == 0 else INK)
        return s

    def callout_slide(self, title, label, items, notes=""):
        s = self.content_slide(title, label, notes)
        n = len(items)
        ch = min(2.3, (H - 2.3 - (n - 1) * 0.3) / n)
        for i, (kind, text) in enumerate(items):
            y = 1.75 + i * (ch + 0.3)
            self.rect(s, 0.85, y, W - 1.9, ch, TINT_AMBER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.05)
            self.rect(s, 0.85, y + 0.1, 0.09, ch - 0.2, AMBER)
            self.text(s, 1.15, y + 0.1, 3, 0.4, kind.upper(), pt=12, color="9A5B00", bold=True)
            self.text(s, 1.15, y + 0.5, W - 2.5, ch - 0.6, text, pt=fit_pt([text], W - 2.6, ch - 0.65, 20, 12), color=INK)
        return s

    def formula_sheet(self, formulas, tmp_dir, part, parts):
        s = self.content_slide("Formula sheet" + (f" ({part}/{parts})" if parts > 1 else ""), "Quick reference")
        cols, rows = 2, 3
        cw, ch = (W - 1.9 - 0.3) / cols, (H - 2.3 - 0.5) / rows
        for i, f in enumerate(formulas):
            x, y = 0.85 + (i % cols) * (cw + 0.3), 1.75 + (i // cols) * (ch + 0.25)
            self.rect(s, x, y, cw, ch, PAPER, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.07)
            label = f.name or f.section
            self.text(s, x + 0.2, y + 0.06, cw - 0.4, 0.35, label[:46], pt=12, color=TEAL, bold=True)
            img = fx.render_png(f.latex, tmp_dir, fontsize=26, color=NAVY) if f.latex else None
            if img:
                self.picture(s, img[0], x + 0.2, y + 0.42, cw - 0.4, ch - 0.55)
            else:
                self.text(s, x + 0.2, y + 0.42, cw - 0.4, ch - 0.55, f.raw, pt=20, color=NAVY, font="Cambria Math", align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        return s

    def end_slide(self):
        s = self.prs.slides.add_slide(self.blank)
        self.n += 1
        self.rect(s, 0, 0, W, H, NAVY)
        self.text(s, 1, 2.7, W - 2, 1, "Keep revising", pt=44, color="FFFFFF", bold=True, font=SERIF, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        self.text(s, 1, 3.8, W - 2, 0.6, "Use the flashcards and quizzes in NoteGenius to lock it in.", pt=18, color="BFD7DA", align=PP_ALIGN.CENTER)
        return s


def _chunks(seq, n):
    return [seq[i:i + n] for i in range(0, len(seq), n)]


def generate_ppt(text, out_dir, title=None, max_slides=MAX_SLIDES):
    """Write a .pptx into out_dir and return (filename, slide_count)."""
    doc = parse(text)
    title = title or doc.title
    kp = key_points(doc, per_section=5, max_words=24)
    stats = doc.stats()
    tmp = os.path.join(out_dir, "_eq")
    os.makedirs(tmp, exist_ok=True)

    deck = Deck(title, title[:60])
    chips = [f"{stats['sections']} sections"] + ([f"{stats['formulas']} formulas"] if stats["formulas"] else []) \
        + ([f"{stats['tables']} tables"] if stats["tables"] else []) + ([f"{stats['definitions']} key terms"] if stats["definitions"] else [])
    deck.title_slide(title, "Study notes deck", chips)

    sections = [s for s in doc.all_sections() if s.title and s.level <= 2]
    has_content = lambda sec: bool(kp.get(sec.uid) or doc.defs_in(sec) or doc.formulas_in(sec) or doc.tables_in(sec))
    sections = [s for s in sections if has_content(s)]
    tops = [s for s in sections if s.level == 1] or sections
    deck.outline_slide([s.title for s in tops][:12])

    budget = max_slides - 16  # a section adds up to ~11 slides; leave room for sheet, takeaways, check and closing
    for sec in sections:
        if deck.n >= budget:
            break
        label = sec.parent.title if sec.parent else (sec.title if False else "")
        pts = kp.get(sec.uid, [])
        defs = doc.defs_in(sec)
        fs = doc.formulas_in(sec)
        ts = doc.tables_in(sec)
        dm = [d.meaning.lower().rstrip(".")[:25] for d in doc.definitions]
        extras = [("Example", b["text"]) for b in sec.own("example")] + [
            ("Note", b["text"]) for b in sec.own("note")
            if b["text"] not in " ".join(pts) and not any(m in b["text"].lower() for m in dm)]
        src = sec.text()
        src_note = f"Source text for this section:\n{src}" if src else ""
        merged = len(pts) + len(defs) <= 6 and (pts or defs) and len(defs) <= 3
        if merged:
            items = [(d.term, compress(d.meaning, 26).rstrip(".")) for d in defs] + pts
            deck.bullets_slide(sec.title, label, items, src_note)
        else:
            if pts:
                for gi, g in enumerate(_chunks(pts, 6)):
                    deck.bullets_slide(sec.title, label, g, src_note, cont=gi > 0)
            for g in _chunks(defs, 4):
                deck.definitions_slide(f"{sec.title}: key terms", label, g, src_note)
        for g in _chunks(fs, 2):
            say = "  ".join(f"{(f.name + ': ') if f.name else ''}{f.speech}." for f in g)
            ctx = "  ".join(f.context for f in g if f.context)
            deck.formulas_slide(f"{sec.title}: formulas" if not any(f.name for f in g) or len(g) > 1 else g[0].name, label, g, tmp,
                                f"Say it aloud: {say}\n{ctx}".strip())
        for t in ts:
            body = t.body
            width = len(t.header)
            if width > 7:
                trimmed = [r[:7] for r in t.rows]
            else:
                trimmed = t.rows
            for ci, chunk in enumerate(_chunks(trimmed[1:], 8)):
                deck.table_slide(t.caption or f"{sec.title}: table", label, [trimmed[0]] + chunk, caption=t.caption if not t.caption else "", cont=ci > 0)
        if extras:
            for g in _chunks(extras, 2):
                deck.callout_slide(f"{sec.title}: worked notes", label, g, src_note)

    if len(doc.formulas) > 3:
        parts = _chunks(doc.formulas, 6)
        for pi, part in enumerate(parts, 1):
            if deck.n < max_slides - 3:
                deck.formula_sheet(part, tmp, pi, len(parts))

    take = top_sentences(doc, 6, 26)
    if take and deck.n < max_slides - 2:
        deck.bullets_slide("Key takeaways", "Summary", take, "Top-ranked sentences from the notes.")
    qs = process_document(doc, 5, seed=7)
    if qs and deck.n < max_slides - 1:
        s = deck.content_slide("Quick check: can you answer these?", "Self-test",
                               "Model answers:\n" + "\n".join(f"{i + 1}. {q['answer']}" for i, q in enumerate(qs)))
        pt = fit_pt([q["question"] for q in qs], W - 3, H - 2.8, 22, 14)
        y = 1.8
        for i, q in enumerate(qs, 1):
            h = max(0.55, _est_lines(q["question"], W - 3.3, pt) * pt * 1.25 / 72 + 0.15)
            deck.rect(s, 0.85, y + 0.04, 0.5, 0.5, AMBER, shape=MSO_SHAPE.OVAL)
            deck.text(s, 0.85, y + 0.04, 0.5, 0.5, str(i), pt=16, color=NAVY, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
            deck.text(s, 1.55, y, W - 3.3, h, q["question"], pt=pt, color=INK)
            deck.text(s, W - 1.6, y + 0.1, 0.9, 0.35, f"{q['marks']} marks", pt=11, color=MUTED, align=PP_ALIGN.RIGHT)
            y += h + 0.2
    deck.end_slide()

    os.makedirs(out_dir, exist_ok=True)
    filename = f"slides_{uuid.uuid4().hex}.pptx"
    deck.prs.save(os.path.join(out_dir, filename))
    return filename, deck.n
