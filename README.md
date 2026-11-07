# NoteGenius: Smart Study Assistant

NoteGenius reads your notes (pasted text, PDF, Word, PowerPoint, TXT/Markdown, or a photo of a page), understands their **structure** (headings, definitions, formulas, tables, lists) and builds study material from it: summaries, flashcards, quizzes, mind maps, slides, formula sheets, study plans and more. Formulas are typeset properly everywhere, and tables stay tables.

<img width="500" height="500" alt="NoteGenius icon" src="https://github.com/user-attachments/assets/b857b05e-7edf-40ec-92fc-bae3a6a540f6" />
<img width="1200" height="700" alt="NoteGenius screenshot" src="https://github.com/user-attachments/assets/99d63887-08a4-4a7d-af87-7956823b0a5c" />
<img width="1200" height="780" alt="NoteGenius screenshot" src="https://github.com/user-attachments/assets/bb60c4d5-ddcd-44e6-a565-440f256c9d0f" />

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

## Writing notes that work best

```
# Motion
Speed is defined as the distance travelled per unit time.

Equations of motion
v = u + at
s = ut + ½at²
where v = final velocity, u = initial velocity, a = acceleration, t = time and s = displacement.

Quantity    Symbol    SI Unit
Force       F         newton (N)
Mass        m         kilogram (kg)

Types of energy:
- Kinetic energy
- Potential energy
```

Everything is optional: plain paragraphs work too, you just get fewer formula, table and term features.

## Honest limits

- It is rule-based, not an AI that "reads" the page. It never invents facts, but it can miss a formula or mis-name one. Use **Notes overview** to check and correct; the fix applies to every tool.
- **PDFs**: bordered tables, headings (by font size/bold), superscripts and subscripts are recovered. Borderless tables and equations drawn as pictures are not. Scanned pages go through text recognition.
- **Photos/handwriting**: printed text works; handwriting and typeset equations are not read reliably.
- Summaries and key points are extracted sentences (shortened at clause boundaries), not rewritten text.

## Run it on your computer

Python 3.10 to 3.12. For mind maps and scanned-page OCR also install [Graphviz](https://graphviz.org/download/) and [Tesseract](https://github.com/tesseract-ocr/tesseract).

```bash
git clone https://github.com/KOLLIVENNELACHOWDARY/NoteGenius.git
cd NoteGenius
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt   # lite install: every tool works
python app.py                     # open http://127.0.0.1:5000
```

Optional neural models (sentence-level answers, KeyBERT, abstractive summaries; about 2 GB RAM): `pip install -r requirements-ml.txt` (Docker: `--build-arg INSTALL_ML=1`). Without them the app falls back automatically.

## Deploy: Vercel + Docker + Google Cloud Run (recommended)

```
Visitors  ->  Vercel (your address, CDN)  ->  Docker container on Google Cloud Run (the real app)
```

The app needs Graphviz (mind maps), Tesseract (scanned pages) and a writable disk, which Vercel's own functions do not give you. So the Docker image runs on **Cloud Run**, and **Vercel** sits in front as the public address using a rewrite (`vercel-proxy/`). Every feature keeps working.

**Cost:** Cloud Run and Vercel Hobby both have free tiers, but Cloud Run needs a billing account with a card, and free-tier terms change. Check the current limits, and set a budget alert in Google Cloud. Vercel Hobby is for non-commercial use.

### Step 1: Deploy the container to Cloud Run (about 10 minutes)
1. Create a Google Cloud project and enable billing (console.cloud.google.com).
2. Open **Cloud Shell** (the `>_` button, top right). It already has `gcloud` and `git`.
3. Run:
   ```bash
   git clone https://github.com/KOLLIVENNELACHOWDARY/NoteGenius.git && cd NoteGenius
   PROJECT=your-project-id bash deploy/cloudrun.sh
   ```
   It builds the Docker image in Google Cloud, deploys it (1 GB RAM, one instance, scales to zero when idle), prints the service URL, and writes `vercel-proxy/vercel.json` for step 2.
4. Test: `bash deploy/check.sh https://YOUR-SERVICE-URL`

### Step 2: Put Vercel in front
1. Commit and push the generated file: `git add vercel-proxy/vercel.json && git commit -m "Point Vercel at Cloud Run" && git push`
2. Vercel dashboard > **Add New > Project** > import the repo > set **Root Directory** to `vercel-proxy` > **Deploy**. Do not deploy the repo root: Vercel would try to build the Python app itself.
3. Open your `*.vercel.app` address and run `bash deploy/check.sh https://your-app.vercel.app`.

### What to expect
- **Cold starts.** After idle time the first request waits for the container to start (often 5 to 15 seconds). Vercel allows a proxied request at most 30 seconds, so the first click after a long idle can time out. Reload and it works.
- **Notes are temporary.** Loaded notes and generated files live in the container's memory and are cleared when it restarts or scales to zero. Students re-add their notes. This is also why the service is limited to one instance.
- **Big uploads.** Vercel limits function request bodies to 4.5 MB. I could not confirm whether that applies to proxied rewrites. If a large PDF fails through the Vercel address, upload through the Cloud Run URL instead; it serves the full app by itself.
- **Redeploy** after code changes: run `bash deploy/cloudrun.sh` again (it keeps your secret key). Vercel needs no redeploy unless the Cloud Run URL changes.

### Other hosts
| Host | Notes |
| --- | --- |
| Render (free web service) | `render.yaml` included. No card, but sleeps after 15 min idle and has only 512 MB RAM and a small CPU share, so slides and mind maps are slow |
| Oracle Cloud free VM | Always on and powerful, but needs a card and manual setup (`docker build` and `docker run -p 80:7860`) |
| Hugging Face Spaces (Docker) | Now needs a paid plan |
| Vercel alone | Not possible without removing mind maps and photo reading and moving notes to an external store |

Measured memory of the default (lite) image: about 200 MB idle, 280 MB after using every tool. Keep a single worker (`--workers 1`): visitor data lives on that instance's disk. Text to speech and YouTube/Google lookups need outbound internet.

Without Docker: install the requirements, then `gunicorn --bind 0.0.0.0:8000 --workers 1 --threads 4 --timeout 300 app:app` behind nginx.

## Configuration

All optional. See `.env.example`.

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Signs the session cookie. If unset, one is generated and stored in `DATA_DIR`. |
| `DATA_DIR` | Uploads, generated files, visitor data. Default `./instance`. |
| `MAX_UPLOAD_MB`, `MAX_TEXT_CHARS`, `FILE_TTL_MINUTES` | Limits. Defaults 15 MB, 120,000 characters, 60 minutes. |
| `COOKIE_SECURE` | Set to `1` when served over HTTPS. |
| `GOOGLE_API_KEY`, `GOOGLE_CSE_ID` | Turns on Google results in "Study resources". |
| `SUMMARY_BACKEND` | `extractive` (default) or `transformer`. |
| `QA_BACKEND` | `auto` (default) or `search` to skip the neural model. |

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
| Mind map says Graphviz is not installed | Install Graphviz, or deploy with the Dockerfile |
| Photo or scanned PDF returns no text | Install Tesseract, or deploy with the Dockerfile |
| Listen says the service could not be reached | The server needs internet access for Google text-to-speech |

## Team details

**Team number**: L05
**Senior Mentor**: Siddhartha
**Junior Mentor**: Charshitha

**Team members**: Vennela, Sathwika, Nikhitha, Gnapika, Madhulika

## What gets ignored when you upload notes

NoteGenius leaves out what is not study content: running headers and footers, page numbers, college / university /
department names, faculty and student details (prepared by, roll no, academic year), cover, certificate and
acknowledgement pages, tables of contents, reference lists and watermark lines. After an upload the page says how many
lines were left out. The rules are conservative (`utils/boilerplate.py`): a sentence that merely mentions a university is kept.

Programs are kept as code (`utils/code.py`). Fenced blocks, fixed-width fonts in PDF and Word, and unmarked C, Java,
Python, SQL or HTML are shown as code and are never turned into formulas, key terms, flashcards or quiz questions.

## Look and feel

Poppins (bundled in `static/fonts`, no external requests), a blue top bar, gradient pill buttons with an icon per tool, rounded cards, dark code boxes and a mobile layout. All styling is in `static/css/style.css` (the "v3 look" block at the end).

## Mind map

`/mindmap` shows the whole notes as one interactive tree: it fits the screen on open, you can zoom, drag, open or close a section, focus on one main section, or go full screen. "Download as picture" makes a Graphviz PNG on demand (`/mindmap/image`). Formulas that cannot be typeset are shown as plain text, never as red errors.

## Notebook features (inspired by NotebookLM)

- **Sources** (`/sources`): add up to 12 sources (pasted notes, PDF, Word, slides, photos), switch each on or off, remove them, and read a short guide for each (summary, topics, questions to ask).
- **Chat with your notes** (`/chat`): answers are built only from your sources and carry numbered citations that name the source and section. If it is not in your sources, it says so.
- **Audio overview** (`/audio-overview`): a two-host conversation about your notes. "Listen in your browser" uses the browser's own voices (no server work). "Make MP3" uses gTTS and needs internet access.
- **Briefing doc, Study guide, FAQ, Timeline**: generated from your sources, printable and downloadable as Markdown.

Everything is rule-based and extractive: it rearranges what your sources say and never adds outside facts. That keeps it fast and free to run, but it cannot rewrite ideas in new words the way a large language model can.
