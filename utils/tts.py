"""Text to speech with gTTS (needs outbound internet access to Google's TTS service). Formulas are read in words."""
import os
import re
import uuid

from .structure import Document, key_points, parse, top_sentences

LANGUAGES = {
    "en": "English", "hi": "Hindi", "te": "Telugu", "ta": "Tamil", "kn": "Kannada", "ml": "Malayalam",
    "mr": "Marathi", "bn": "Bengali", "fr": "French", "es": "Spanish", "de": "German",
}
MAX_CHARS = 5000


def speakable(doc, scope="summary"):
    """Plain spoken text for the notes. scope: 'summary', 'full', or a section title."""
    parts = []
    if scope == "summary":
        parts.append(f"Summary of {doc.title}.")
        kp = key_points(doc, per_section=2)
        for sec in doc.all_sections():
            pts = kp.get(sec.uid, [])
            if pts and sec.title:
                parts.append(f"{sec.title}. " + " ".join(p.rstrip("…") + ("" if p.endswith((".", "!", "?")) else ".") for p in pts[:2]))
        for f in doc.formulas[:6]:
            parts.append((f"{f.name}: " if f.name else "Formula: ") + f.speech + ".")
        return " ".join(parts)
    for sec in doc.all_sections():
        if scope != "full" and sec.title != scope:
            continue
        if sec.title:
            parts.append(sec.title + ".")
        for b in sec.blocks:
            k = b["kind"]
            if k in ("para", "note", "example"):
                text = b["text"]
                from . import formulas as fx

                for raw in fx.find_inline_formulas(text):
                    text = text.replace(raw, fx.to_speech(raw))
                parts.append(text)
            elif k == "list":
                parts.append((b["label"] + ". " if b["label"] else "") + " ".join(i.rstrip(".") + "." for i in b["items"]))
            elif k == "formula":
                parts.append((b["name"] + ": " if b["name"] else "Formula: ") + __import__("utils.formulas", fromlist=["x"]).to_speech(b["raw"], b["latex"]) + ".")
            elif k == "table":
                header = b["rows"][0]
                for row in b["rows"][1:]:
                    parts.append(", ".join(f"{h} {v}" for h, v in zip(header, row) if v) + ".")
    return " ".join(parts)


def text_to_speech(text, out_dir, lang="en"):
    """Write an MP3 into out_dir and return its filename."""
    from gtts import gTTS

    if lang not in LANGUAGES:
        raise ValueError("Unsupported language.")
    text = re.sub(r"\s+", " ", text)[:MAX_CHARS]
    if not text.strip():
        raise ValueError("There is no text to read aloud.")
    os.makedirs(out_dir, exist_ok=True)
    filename = f"speech_{uuid.uuid4().hex}.mp3"
    try:
        gTTS(text=text, lang=lang, slow=False).save(os.path.join(out_dir, filename))
    except Exception as exc:
        raise RuntimeError(
            "The text-to-speech service could not be reached. The server needs internet access for this tool."
        ) from exc
    return filename
