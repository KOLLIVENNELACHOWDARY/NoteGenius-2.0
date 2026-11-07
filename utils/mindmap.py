"""Mind maps drawn with Graphviz: one overview of the whole notes plus a detailed map per main section.

Nodes are styled by what they hold: key points, definitions (term in bold), formulas (typeset image),
and tables (a small preview of the real table).
"""
import html
import os
import re
import textwrap
import uuid

from . import formulas as fx
from .structure import Document, compress, key_points, parse

PALETTE = [
    ("#0F6B6B", "#DDF1F0"), ("#B4551B", "#FBE6D4"), ("#5B4BB7", "#E6E2F8"), ("#2F7D32", "#E1F2DF"),
    ("#B03A6E", "#F8E0EB"), ("#1F5FA8", "#DCE9F8"), ("#8A6D00", "#F7EFC9"), ("#475569", "#E5E9EE"),
]
NAVY = "#12263F"
MAX_SECTION_MAPS = 8


def _wrap(text, width=34, max_lines=4):
    lines = textwrap.wrap(re.sub(r"\s+", " ", text), width) or [""]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,; ") + "…"
    return lines


def _esc(t):
    return html.escape(t, quote=True)


def _table(rows, bg, border, font=11):
    return (f'<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="{5}" STYLE="rounded" BGCOLOR="{bg}" COLOR="{border}">'
            + "".join(rows) + "</TABLE>>")


def _row(text_lines, color="#1B2A41", bold=False, size=12, align="LEFT"):
    body = f'<BR ALIGN="{align}"/>'.join(_esc(l) for l in text_lines)
    if bold:
        body = f"<B>{body}</B>"
    return f'<TR><TD ALIGN="{align}"><FONT POINT-SIZE="{size}" COLOR="{color}">{body}</FONT><BR ALIGN="{align}"/></TD></TR>'


def _node_label(kind, data, accent, tint, tmp_dir):
    if kind == "root":
        return _table([_row(_wrap(data, 26, 3), "white", True, 18, "CENTER")], NAVY, NAVY)
    if kind == "section":
        return _table([_row(_wrap(data, 28, 3), "white", True, 14, "CENTER")], accent, accent)
    if kind == "point":
        return _table([_row(_wrap(data, 38, 4), "#1B2A41", False, 12)], "white", accent)
    if kind == "def":
        term, meaning = data
        return _table([_row([term], accent, True, 13), _row(_wrap(compress(meaning, 16), 36, 3), "#1B2A41", False, 11)], tint, accent)
    if kind == "formula":
        f = data
        rows = []
        if f.name:
            rows.append(_row(_wrap(f.name, 30, 2), accent, True, 11))
        img = fx.render_png(f.latex, tmp_dir, fontsize=11, color=NAVY) if f.latex else None
        if img:
            rows.append(f'<TR><TD><IMG SRC="{img[0]}"/></TD></TR>')
        else:
            rows.append(_row(_wrap(f.raw, 34, 2), NAVY, True, 13))
        return _table(rows, "#FFFBEA", "#D9A400")
    if kind == "table":
        t = data
        cols = min(len(t.header), 4)
        rows = []
        if t.caption or t.section:
            rows.append(f'<TR><TD COLSPAN="{cols}" ALIGN="LEFT"><FONT POINT-SIZE="10" COLOR="{accent}"><B>{_esc((t.caption or t.section)[:40])}</B></FONT></TD></TR>')
        rows.append("<TR>" + "".join(f'<TD BGCOLOR="{accent}"><FONT COLOR="white" POINT-SIZE="10"><B>{_esc(c[:20])}</B></FONT></TD>' for c in t.header[:cols]) + "</TR>")
        for r in t.body[:3]:
            rows.append("<TR>" + "".join(f'<TD><FONT POINT-SIZE="10">{_esc(c[:26])}</FONT></TD>' for c in r[:cols]) + "</TR>")
        if len(t.body) > 3:
            rows.append(f'<TR><TD COLSPAN="{cols}"><FONT POINT-SIZE="9" COLOR="#5B677A">+ {len(t.body) - 3} more rows</FONT></TD></TR>')
        return (f'<<TABLE BORDER="1" CELLBORDER="1" CELLSPACING="0" CELLPADDING="3" BGCOLOR="white" COLOR="{accent}">'
                + "".join(rows) + "</TABLE>>")
    raise ValueError(kind)


class _Map:
    def __init__(self, tmp_dir, dpi=120):
        from graphviz import Digraph

        self.g = Digraph("G", format="png")
        self.g.attr(rankdir="LR", splines="spline", pad="0.35", nodesep="0.28", ranksep="0.9", dpi=str(dpi), bgcolor="white")
        self.g.attr("node", shape="plain", fontname="Helvetica")
        self.g.attr("edge", arrowhead="none", penwidth="1.6")
        self.tmp = tmp_dir
        self.n = 0
        self.count = 0

    def node(self, kind, data, accent, tint):
        self.n += 1
        self.count += 1
        nid = f"n{self.n}"
        self.g.node(nid, label=_node_label(kind, data, accent, tint, self.tmp))
        return nid

    def edge(self, a, b, color):
        self.g.edge(a, b, color=color)

    def render(self, out_dir):
        os.makedirs(out_dir, exist_ok=True)
        name = f"mindmap_{uuid.uuid4().hex}"
        self.g.render(filename=name, directory=out_dir, cleanup=True)
        return f"{name}.png"


def _fill_section(m, parent_id, sec, doc, kp, accent, tint, depth, detailed):
    pts = kp.get(sec.uid, [])[: (5 if detailed else 2)]
    defs = doc.defs_in(sec)[: (4 if detailed else 1)]
    fs = doc.formulas_in(sec)[: (4 if detailed else 2)]
    ts = doc.tables_in(sec)[: (2 if detailed else 1)]
    for d in defs:
        m.edge(parent_id, m.node("def", (d.term, d.meaning), accent, tint), accent)
    for f in fs:
        m.edge(parent_id, m.node("formula", f, accent, tint), "#D9A400")
    for t in ts:
        m.edge(parent_id, m.node("table", t, accent, tint), accent)
    shown = {d.meaning[:30].lower() for d in defs}
    for p in pts:
        if p[:30].lower() in shown:
            continue
        m.edge(parent_id, m.node("point", p, accent, tint), accent)
    if depth > 0:
        for child in sec.children:
            cid = m.node("section", child.title, accent, tint)
            m.edge(parent_id, cid, accent)
            _fill_section(m, cid, child, doc, kp, accent, tint, depth - 1, detailed)


def _has_content(sec, doc, kp):
    return bool(kp.get(sec.uid)) or bool(doc.defs_in(sec)) or bool(doc.formulas_in(sec)) or bool(doc.tables_in(sec)) \
        or any(_has_content(c, doc, kp) for c in sec.children)


def build_tree(text):
    """The whole notes as one tree for the on-page mind map: root -> sections -> terms, formulas, tables, points."""
    doc = parse(text)
    kp = key_points(doc, per_section=4, max_words=22)
    top = [s for s in doc.sections if s.title and _has_content(s, doc, kp)]
    if not top:
        raise ValueError("There is not enough structure in these notes to draw a mind map. Try longer notes with headings.")
    count = [1]

    def leaf(**kw):
        count[0] += 1
        return kw

    def section(sec, idx, depth):
        accent, tint = PALETTE[idx % len(PALETTE)]
        kids = []
        defs = doc.defs_in(sec)[:4]
        for d in defs:
            kids.append(leaf(kind="def", term=d.term, meaning=compress(d.meaning, 18)))
        for f in doc.formulas_in(sec)[:4]:
            kids.append(leaf(kind="formula", name=f.name, latex=f.latex, raw=f.raw))
        for t in doc.tables_in(sec)[:2]:
            cols = min(len(t.header), 4)
            kids.append(leaf(kind="table", caption=(t.caption or t.section)[:50], header=[c[:22] for c in t.header[:cols]],
                             rows=[[c[:28] for c in r[:cols]] for r in t.body[:3]], more=max(0, len(t.body) - 3)))
        shown = {d.meaning[:30].lower() for d in defs}
        for p in kp.get(sec.uid, [])[:4]:
            if p[:30].lower() not in shown:
                kids.append(leaf(kind="point", text=p))
        if depth < 3:
            for child in sec.children:
                if _has_content(child, doc, kp):
                    kids.append(section(child, idx, depth + 1))
        count[0] += 1
        return {"kind": "section", "title": sec.title, "color": accent, "tint": tint, "depth": depth, "children": kids,
                "collapsed": depth >= 2 and bool(kids)}

    branches = [section(sec, i, 1) for i, sec in enumerate(top)]
    return {"kind": "root", "title": doc.title, "children": branches, "nodes": count[0] + 1}


def generate_mindmaps(text, out_dir, sections=True):
    """Render maps into out_dir. Returns [{'title','file','kind','nodes'}]; the first is the overview."""
    from graphviz.backend import ExecutableNotFound

    doc = parse(text)
    kp = key_points(doc, per_section=4, max_words=22)
    tmp = os.path.join(out_dir, "_eq")
    os.makedirs(tmp, exist_ok=True)
    top = [s for s in doc.sections if s.title and _has_content(s, doc, kp)]
    if not top:
        raise ValueError("There is not enough structure in these notes to draw a mind map. Try longer notes with headings.")
    maps = []
    try:
        ov = _Map(tmp)
        root = ov.node("root", doc.title, NAVY, "#fff")
        for i, sec in enumerate(top):
            accent, tint = PALETTE[i % len(PALETTE)]
            sid = ov.node("section", sec.title, accent, tint)
            ov.edge(root, sid, accent)
            _fill_section(ov, sid, sec, doc, kp, accent, tint, 1, detailed=False)
        maps.append({"title": "Overview", "file": ov.render(out_dir), "kind": "overview", "nodes": ov.count})

        for i, sec in enumerate(top[:MAX_SECTION_MAPS] if sections else []):
            accent, tint = PALETTE[i % len(PALETTE)]
            mm = _Map(tmp)
            rid = mm.node("root", sec.title, NAVY, "#fff")
            _fill_section(mm, rid, sec, doc, kp, accent, tint, 2, detailed=True)
            if mm.count <= 2:
                continue
            maps.append({"title": sec.title, "file": mm.render(out_dir), "kind": "section", "nodes": mm.count})
    except ExecutableNotFound as exc:
        raise RuntimeError(
            "Graphviz is not installed on this server, so mind maps are unavailable. "
            "Install it (for example: apt-get install graphviz) or use the Docker image."
        ) from exc
    return maps


def generate_mindmap(text, out_dir, fmt="png"):
    """Backward-compatible: return the filename of the overview map."""
    return generate_mindmaps(text, out_dir)[0]["file"]
