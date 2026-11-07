# NoteGenius: Smart Study Assistant

NoteGenius reads your notes (pasted text, PDF, Word, PowerPoint, TXT/Markdown, or a photo of a page), understands their **structure** (headings, definitions, formulas, tables, lists) and builds study material from it: summaries, flashcards, quizzes, mind maps, slides, formula sheets, study plans and more. Formulas are typeset properly everywhere, and tables stay tables.

## What it understands

| In your notes | What NoteGenius does with it |
| --- | --- |
| Headings (`# Title`, `1. Title`, `Chapter 2`, big or bold text in PDFs/Word) | Builds sections used by every tool |
| Formulas: `v = u + at`, `E = mc^2`, `x² + y² = r²`, `x = (-b ± sqrt(b^2-4ac)) / (2a)`, `$\frac{a}{b}$`, Word equations, chemical equations `2H2 + O2 -> 2H2O` | Typeset as real equations; names and symbol meanings are attached |
| "where v = final velocity, u = ..." | Becomes the symbol legend for the formula above it |
| Tables (`\|` tables, tab or column-aligned text, Word tables, bordered PDF tables) | Shown as tables, drawn as real PowerPoint tables, turned into flashcards and quiz questions |
| Definitions ("X is defined as...", "X: meaning", "... is called X") | Glossary, flashcards, quiz, mind map |
| Bullet lists | Kept as author-written key points, used for acronym mnemonics |
| "Note:", "Important:", "Example" | Highlighted callouts in slides and summaries |

## Tools

| Group | Tool | What you get |
| --- | --- | --- |
| Understand | **Notes overview** | What was found (sections, formulas, tables, terms), plus an editor to correct the text |
| | **Summary** | Overview, key points per section, terms, formulas, tables. Brief / standard / detailed. Download as Markdown |
| | **Mind maps** | An overview map plus a detailed map per section. Definitions, typeset formulas and table previews as colour-coded nodes |
| | **Slides** | Designed PowerPoint: outline, key points, term cards, typeset formulas with symbol legends, native tables, callouts, formula sheet, takeaways, self-test, speaker notes |
| Memorise | **Flashcards** | Definitions, formulas, symbols, table facts, lists, fill-in facts. Study mode with a review loop, keyboard shortcuts, filters, Anki/Quizlet CSV export |
| | **Formula sheet** | Every formula typeset, grouped by section, copyable as LaTeX, printable |
| | **Glossary** | Searchable key terms |
| | **Mnemonics** | Acronyms from your own lists, plus a picture-word sentence |
| | **Listen** | Text to speech in 11 languages. Formulas are read in words ("v equals u plus a t") |
| Test yourself | **Quiz** | Terms, formulas, symbols, table lookups, fill-in-the-blank. Pick types and difficulty. Review and retry what you missed |
| | **Practice questions** | Exam-style questions with marks and model answers |
| | **Ask your notes** | "define speed", "formula for kinetic energy", "SI unit of force" |
| Plan | **Study plan** | Day-by-day schedule to your exam date, then revision and a final check |
| | **Cheat sheet** | One printable page: formulas, terms, key points, tables |
| | **Study resources** | YouTube and (optional) Google results |


## Honest limits

- It is rule-based, not an AI that "reads" the page. It never invents facts, but it can miss a formula or mis-name one. Use **Notes overview** to check and correct; the fix applies to every tool.
- **PDFs**: bordered tables, headings (by font size/bold), superscripts and subscripts are recovered. Borderless tables and equations drawn as pictures are not. Scanned pages go through text recognition.
- **Photos/handwriting**: printed text works; handwriting and typeset equations are not read reliably.
- Summaries and key points are extracted sentences (shortened at clause boundaries), not rewritten text.

## Run it on your computer

Python 3.10 to 3.12. For mind maps and scanned-page OCR also install [Graphviz](https://graphviz.org/download/) and [Tesseract](https://github.com/tesseract-ocr/tesseract).

```bash
git clone https://github.com/KOLLIVENNELACHOWDARY/NoteGenius 2.0.git
cd NoteGenius 2.0
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt   # lite install: every tool works
python app.py                     # open http://127.0.0.1:5000
```

Additional neural models (sentence-level answers, KeyBERT, abstractive summaries; about 2 GB RAM): `pip install -r requirements-ml.txt` (Docker: `--build-arg INSTALL_ML=1`). Without them the app falls back automatically.

## Project layout

```
app.py                 Flask app: routes, upload handling, CSRF, security headers
utils/structure.py     The notes parser (sections, definitions, formulas, tables) + key-point ranking
utils/formulas.py      Equation detection, plain-text/Unicode/LaTeX conversion, speech, equation images
utils/extract.py       File readers (PDF, DOCX incl. Word equations, PPTX, images/OCR)
utils/*.py             One module per tool (flashcards, mindmap, pptgen, mcq_generator, ...)
templates/, static/    Pages, CSS, JS, bundled KaTeX (no CDN needed)
tests/                 pytest suite (85 tests)
legacy/                Original standalone scripts, kept for reference
Dockerfile             Production image (lite by default)
deploy/                Cloud Run deploy script and health check
vercel-proxy/          Tiny Vercel project that forwards to Cloud Run
```

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

## Security notes

- Secrets come from environment variables. Nothing is hardcoded.
- Uploads are limited by size and type, saved under random names, and deleted right after text extraction.
- Generated files are served only from a fixed folder and only if the name matches the generated pattern.
- Forms are CSRF-protected. Scripts are same-origin only (`script-src 'self'`); styles allow inline because KaTeX positions maths with style attributes.
- Notes are stored server-side (the cookie holds only a random id) and purged after a few hours.
- There is no login or rate limiting. For a public site, add your host's rate limiting.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| A formula shows as plain text | Check the **Notes overview**; write it on its own line or inside `$...$` |
| A table is missing | Use `\|` separators or two or more spaces between columns, and keep rows on consecutive lines |
| Mind map says Graphviz is not installed | Install Graphviz |
| Photo or scanned PDF returns no text | Install Tesseract |
| Listen says the service could not be reached | The server needs internet access for Google text-to-speech |

----
**Author**
---
KOLLI VENNELA CHOWDARY

------
**Liscence**
---
This project is intended for educational purposes.


