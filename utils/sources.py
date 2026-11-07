"""A notebook holds several sources (pasted notes, PDFs, Word files ...). Tools work on the combined text of the sources
that are switched on. With one source the text is used as it is; with several, each source becomes its own top-level section."""
import re
import uuid

MAX_SOURCES = 12
MARK = "@@source: "  # the parser turns this line into a top-level section


def default_name(text, fallback="Notes"):
    for line in text.splitlines():
        t = line.strip()
        if not t:
            continue
        t = re.sub(r"^#{1,6}\s*", "", t).strip(" *_|-")
        if t and not t.startswith(("$", "```")):
            return (t[:57] + "…") if len(t) > 58 else t
    return fallback


def make_source(name, text):
    return {"id": uuid.uuid4().hex[:10], "name": (name or "Notes").strip()[:80] or "Notes", "text": text, "on": True,
            "words": len(re.findall(r"\w+", text))}


def combine(sources):
    on = [s for s in sources if s.get("on", True) and s.get("text", "").strip()]
    if not on:
        return ""
    if len(on) == 1:
        return on[0]["text"]
    return "\n\n".join(f"{MARK}{s['name']}\n\n{s['text']}" for s in on)
