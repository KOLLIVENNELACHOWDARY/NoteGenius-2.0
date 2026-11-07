"""NoteGenius: turn notes (text, formulas, tables) into summaries, flashcards, quizzes, mind maps, slides and more."""
import datetime as dt
import logging
import os
import re
import secrets
import time
import uuid
from datetime import timedelta

from flask import Flask, Response, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.utils import secure_filename

from utils import store
from utils.extract import ALLOWED_EXTENSIONS, ExtractionError, extract_with_report
from utils import sources as srclib
from utils.structure import parse, reading_minutes
from utils.tts import LANGUAGES as TTS_LANGUAGES

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("notegenius")

TOOLS = [
    ("Your notebook", [
        ("sources", "Sources", "Add several files and notes. Switch each on or off. See a guide to every source."),
        ("chat", "Chat with your notes", "Ask anything. Answers come only from your sources, with numbered citations."),
        ("audio_overview", "Audio overview", "Two hosts talk through your notes. Listen in your browser or make an MP3."),
        ("briefing", "Briefing doc", "A one-page brief: overview, key points, terms and formulas."),
        ("studyguide", "Study guide", "Short-answer questions with answer key, essay questions and a glossary."),
        ("faq", "FAQ", "The questions your notes answer, with short answers."),
        ("timeline", "Timeline", "Dated events found in your sources, in order."),
    ]),
    ("Understand your notes", [
        ("overview", "Notes overview", "See what was found: sections, formulas, tables, terms. Fix mistakes."),
        ("summary", "Summary", "Overview, key points per section, terms, formulas and tables."),
        ("mindmap", "Mind maps", "An overview map and a detailed map per section, with typeset formulas."),
        ("ppt", "Slides", "A designed PowerPoint with formulas, tables and speaker notes."),
    ]),
    ("Memorise", [
        ("flashcards", "Flashcards", "Study mode with review loop. Exports to Anki."),
        ("formulas", "Formula sheet", "Every formula, typeset, with what each symbol means."),
        ("glossary", "Glossary", "All key terms, searchable."),
        ("mnemonic", "Mnemonics", "Acronyms built from your own lists."),
        ("tts", "Listen", "Hear your notes. Formulas are read in words."),
    ]),
    ("Test yourself", [
        ("mcq", "Multiple-choice quiz", "Terms, formulas, symbols, tables. Retry what you missed."),
        ("qgen", "Practice questions", "Exam-style questions with marks and model answers."),
        ("qna", "Ask your notes", "Ask a question, get the answer from your notes."),
    ]),
    ("Plan and revise", [
        ("studyplan", "Study plan", "A day-by-day schedule up to your exam."),
        ("cheatsheet", "Cheat sheet", "One printable revision page."),
        ("suggestions", "Study resources", "Videos and links on the same topics."),
    ]),
]
_FILE_RE = re.compile(r"^(mindmap|speech|slides)_[0-9a-f]{32}\.(png|mp3|pptx)$")
QUIZ_TYPES = [
    ("definition", "Terms and definitions"), ("formula", "Formulas"), ("symbol", "What each symbol means"),
    ("table", "Tables"), ("cloze", "Fill in the blank"),
]


def _truthy(value):
    return str(value).lower() in ("1", "true", "yes", "on")


def _clamp(value, default, low, high):
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _load_secret_key(app):
    """SECRET_KEY env var, else a key generated once and kept in DATA_DIR (never committed)."""
    key = app.config.get("SECRET_KEY") or os.environ.get("SECRET_KEY")
    if key:
        return key
    path = os.path.join(app.config["DATA_DIR"], "secret_key")
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except FileNotFoundError:
        key = secrets.token_hex(32)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(key)
        return key


def create_app(test_config=None):
    app = Flask(__name__)
    on_vercel = bool(os.environ.get("VERCEL"))  # Vercel's project folder is read-only; only /tmp can be written
    if on_vercel:
        os.environ.setdefault("NLTK_DATA", "/tmp/nltk_data")
    data_dir = os.environ.get("DATA_DIR") or ("/tmp/notegenius" if on_vercel else os.path.join(app.root_path, "instance"))
    app.config.update(
        DATA_DIR=data_dir,
        MAX_CONTENT_LENGTH=_clamp(os.environ.get("MAX_UPLOAD_MB"), 15, 1, 100) * 1024 * 1024,
        MAX_TEXT_CHARS=_clamp(os.environ.get("MAX_TEXT_CHARS"), 120000, 1000, 500000),
        FILE_TTL_SECONDS=_clamp(os.environ.get("FILE_TTL_MINUTES"), 60, 5, 1440) * 60,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE=os.environ.get("COOKIE_SAMESITE", "Lax"),
        SESSION_COOKIE_SECURE=_truthy(os.environ.get("COOKIE_SECURE", "0")),
        PERMANENT_SESSION_LIFETIME=timedelta(hours=3),
        GOOGLE_API_KEY=os.environ.get("GOOGLE_API_KEY", ""),
        GOOGLE_CSE_ID=os.environ.get("GOOGLE_CSE_ID", ""),
    )
    if test_config:
        app.config.update(test_config)
    data_dir = app.config["DATA_DIR"]
    app.config.setdefault("GENERATED_DIR", os.path.join(data_dir, "generated"))
    app.config.setdefault("UPLOAD_DIR", os.path.join(data_dir, "uploads"))
    for key in ("DATA_DIR", "GENERATED_DIR", "UPLOAD_DIR"):
        os.makedirs(app.config[key], exist_ok=True)
    app.secret_key = _load_secret_key(app)
    app.config["_last_cleanup"] = 0.0

    # ---------------------------------------------------------------- hooks
    def housekeeping():
        """Delete old generated files, uploads and visitor state (at most every 10 minutes)."""
        now = time.time()
        if now - app.config["_last_cleanup"] < 600:
            return
        app.config["_last_cleanup"] = now
        ttl = app.config["FILE_TTL_SECONDS"]
        store.purge_dir(app.config["GENERATED_DIR"], ttl)
        store.purge_dir(os.path.join(app.config["GENERATED_DIR"], "_eq"), ttl)
        store.purge_dir(app.config["UPLOAD_DIR"], 600)
        store.purge_dir(os.path.join(app.config["DATA_DIR"], "sessions"), 6 * 3600)

    @app.before_request
    def protect():
        housekeeping()
        if request.method == "POST":
            expected = session.get("csrf_token")
            sent = request.form.get("csrf_token", "")
            if not expected or not sent or not secrets.compare_digest(expected, sent):
                abort(400, "Your session expired. Reload the page and try again.")

    @app.after_request
    def security_headers(resp):
        # Pages are per-visitor, so no CDN or proxy (for example Vercel in front of this app) may cache them.
        if request.endpoint == "static":
            resp.headers["Cache-Control"] = "public, max-age=3600"
        else:
            resp.headers["Cache-Control"] = "private, no-store"
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        # Scripts stay strictly same-origin. Styles allow inline because KaTeX positions maths with style attributes.
        resp.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; media-src 'self'; font-src 'self'; "
            "script-src 'self'; style-src 'self' 'unsafe-inline'; form-action 'self'; base-uri 'self'; frame-ancestors 'self'",
        )
        return resp

    @app.context_processor
    def inject():
        def csrf_token():
            if "csrf_token" not in session:
                session["csrf_token"] = secrets.token_hex(16)
            return session["csrf_token"]

        text = store.get("text", "")
        return {"csrf_token": csrf_token, "notes_words": len(text.split())}

    # -------------------------------------------------------------- helpers
    def current_text():
        return store.get("text", "")

    def source_list():
        return store.get("sources") or []

    def multi_sources():
        return sum(1 for x in source_list() if x.get("on", True)) > 1

    def rebuild(sources, keep_chat=False):
        text = srclib.combine(sources)
        if len(text) > app.config["MAX_TEXT_CHARS"]:
            text = text[: app.config["MAX_TEXT_CHARS"]]
            flash(f"Your notes were long, so only the first {len(text):,} characters are used.", "info")
        values = {"sources": sources, "text": text, "quiz": None, "last_quiz": None}
        if not keep_chat:
            values["chat"] = []
        store.update(**values)

    def need_notes():
        flash("Add your notes first.", "info")
        return redirect(url_for("index"))

    def posted_text(fallback):
        text = request.form.get("text", "").strip()[: app.config["MAX_TEXT_CHARS"]]
        return text or fallback

    def run(func, *args, **kwargs):
        """Run a tool; return (result, error_message)."""
        try:
            return func(*args, **kwargs), None
        except (RuntimeError, ValueError) as exc:
            return None, str(exc)
        except Exception:
            log.exception("Tool failed: %s", getattr(func, "__name__", func))
            return None, "Something went wrong while processing your notes. Try shorter or simpler text."

    def save_notes(text, name=None, add=False):
        """Replace the notebook with one source, or (add=True) add another source."""
        text = text[: app.config["MAX_TEXT_CHARS"]]
        name = name or srclib.default_name(text, "Pasted notes")
        if add:
            sources = source_list()
            if len(sources) >= srclib.MAX_SOURCES:
                flash(f"A notebook holds up to {srclib.MAX_SOURCES} sources. Remove one first.", "error")
                return False
            sources = sources + [srclib.make_source(name, text)]
        else:
            sources = [srclib.make_source(name, text)]
        rebuild(sources)
        return True

    # --------------------------------------------------------------- routes
    @app.get("/")
    def index():
        return render_template("index.html", allowed=sorted(e.lstrip(".") for e in ALLOWED_EXTENSIONS),
                               max_mb=app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024))

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.route("/text_input", methods=["GET", "POST"])
    def text_input():
        if request.method == "GET":
            return redirect(url_for("index"))
        text = request.form.get("input_text", "").strip()
        if len(text) < 20:
            flash("Enter at least a couple of sentences of notes.", "error")
            return redirect(url_for("index"))
        if request.form.get("add"):
            save_notes(text, request.form.get("name", "").strip() or None, add=True)
            return redirect(url_for("sources"))
        save_notes(text)
        return redirect(url_for("operations"))

    @app.route("/upload_file", methods=["GET", "POST"])
    def upload_file():
        if request.method == "GET":
            return redirect(url_for("index"))
        upload = request.files.get("uploaded_file")
        if not upload or not upload.filename:
            flash("Choose a file to upload.", "error")
            return redirect(url_for("index"))
        ext = os.path.splitext(secure_filename(upload.filename))[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            flash("That file type is not supported. Use PDF, DOCX, PPTX, TXT, MD, PNG or JPG.", "error")
            return redirect(url_for("index"))
        path = os.path.join(app.config["UPLOAD_DIR"], f"{uuid.uuid4().hex}{ext}")
        upload.save(path)
        try:
            text, ignored = extract_with_report(path)
        except ExtractionError as exc:
            flash(str(exc), "error")
            return redirect(url_for("index"))
        except Exception:
            log.exception("File extraction failed")
            flash("That file could not be processed.", "error")
            return redirect(url_for("index"))
        finally:
            try:
                os.remove(path)
            except OSError:
                pass
        adding = bool(request.form.get("add"))
        if not save_notes(text, os.path.splitext(secure_filename(upload.filename))[0].replace("_", " ") or None, add=adding):
            return redirect(url_for("sources"))
        msg = "File read. Check the overview to make sure formulas, tables and code were picked up correctly."
        if ignored:
            msg += f" Left out {len(ignored)} header, footer or cover-page lines (college names, page numbers and similar)."
        flash(msg, "info")
        return redirect(url_for("sources") if adding else url_for("operations"))

    @app.get("/operations")
    def operations():
        text = current_text()
        if not text:
            return need_notes()
        doc = parse(text)
        return render_template("operations.html", tools=TOOLS, stats=doc.stats(), minutes=reading_minutes(doc), title=doc.title)

    @app.route("/overview", methods=["GET", "POST"])
    def overview():
        text = current_text()
        if not text:
            return need_notes()
        if request.method == "POST":
            new = request.form.get("text", "").strip()
            if len(new) < 20:
                flash("Notes cannot be empty.", "error")
            else:
                save_notes(new, "Edited notes")
                flash("Notes updated. Every tool now uses the new version.", "info")
            return redirect(url_for("overview"))
        doc = parse(text)
        return render_template("overview.html", doc=doc, text=text, stats=doc.stats())

    @app.route("/summary", methods=["GET", "POST"])
    def summary():
        text = current_text()
        if not text:
            return need_notes()
        from utils.summary import summarize_document

        level = request.values.get("level", "standard")
        result, error = run(summarize_document, text, level)
        return render_template("summary.html", result=result, error=error, level=level)

    @app.get("/summary.md")
    def summary_md():
        text = current_text()
        if not text:
            return need_notes()
        from utils.summary import summarize_document, to_markdown

        result, error = run(summarize_document, text, request.args.get("level", "standard"))
        if error:
            abort(500)
        return Response(to_markdown(result), mimetype="text/markdown",
                        headers={"Content-Disposition": 'attachment; filename="NoteGenius-summary.md"'})

    @app.get("/flashcards")
    def flashcards():
        text = current_text()
        if not text:
            return need_notes()
        from utils.flashcards import TYPE_LABELS, build_cards

        count = _clamp(request.args.get("n"), 60, 5, 200)
        cards, error = run(build_cards, parse(text), count)
        if cards is not None and not cards:
            error = "No cards could be made. Try notes with definitions, formulas, lists or tables."
        counts = {}
        for c in cards or []:
            counts[c["type"]] = counts.get(c["type"], 0) + 1
        return render_template("flashcards.html", cards=cards or [], error=error, count=count, labels=TYPE_LABELS, counts=counts)

    @app.get("/flashcards.csv")
    def flashcards_csv():
        text = current_text()
        if not text:
            return need_notes()
        from utils.flashcards import build_cards, cards_to_csv

        cards = build_cards(parse(text), _clamp(request.args.get("n"), 200, 5, 400))
        return Response("\ufeff" + cards_to_csv(cards), mimetype="text/csv",
                        headers={"Content-Disposition": 'attachment; filename="NoteGenius-flashcards.csv"'})

    @app.get("/formulas")
    def formulas():
        text = current_text()
        if not text:
            return need_notes()
        return render_template("formulas.html", doc=parse(text))

    @app.get("/glossary")
    def glossary():
        text = current_text()
        if not text:
            return need_notes()
        doc = parse(text)
        terms = sorted(doc.definitions, key=lambda d: d.term.lower())
        return render_template("glossary.html", terms=terms)

    @app.get("/cheatsheet")
    def cheatsheet():
        text = current_text()
        if not text:
            return need_notes()
        from utils.summary import summarize_document

        result, error = run(summarize_document, text, "brief")
        return render_template("cheatsheet.html", result=result, error=error)

    @app.route("/studyplan", methods=["GET", "POST"])
    def studyplan():
        text = current_text()
        if not text:
            return need_notes()
        plan = error = None
        form = {"days": request.form.get("days", "7"), "minutes": request.form.get("minutes", "60"), "exam": request.form.get("exam", "")}
        if request.method == "POST":
            from utils.studyplan import build_plan

            days = _clamp(form["days"], 7, 1, 60)
            if form["exam"]:
                try:
                    exam = dt.date.fromisoformat(form["exam"])
                    days = (exam - dt.date.today()).days
                    if days < 1:
                        error = "Pick an exam date in the future."
                    days = max(1, min(60, days))
                except ValueError:
                    error = "That exam date is not valid."
            if not error:
                plan, error = run(build_plan, text, days, _clamp(form["minutes"], 60, 15, 600))
        return render_template("studyplan.html", plan=plan, error=error, form=form, today=dt.date.today().isoformat())

    @app.route("/qgen", methods=["GET", "POST"])
    def qgen():
        text = current_text()
        if not text:
            return need_notes()
        questions = error = None
        count = _clamp(request.form.get("num_questions"), 8, 1, 30)
        if request.method == "POST":
            from utils.ques_gen import process_document

            questions, error = run(process_document, parse(text), count, None)
            if questions is not None and not questions:
                error = "No questions could be made from these notes. Try longer notes with definitions or formulas."
        return render_template("qgen.html", questions=questions, error=error, count=count)

    @app.get("/mindmap")
    def mindmap():
        text = current_text()
        if not text:
            return need_notes()
        from utils.mindmap import build_tree

        tree, error = run(build_tree, text)
        return render_template("mindmap.html", tree=tree, error=error)

    @app.get("/mindmap/image")
    def mindmap_image():
        text = current_text()
        if not text:
            return need_notes()
        from utils.mindmap import generate_mindmaps

        maps, error = run(generate_mindmaps, text, app.config["GENERATED_DIR"], False)
        if error or not maps:
            flash(error or "The picture could not be made.", "error")
            return redirect(url_for("mindmap"))
        return redirect(url_for("download", name=maps[0]["file"]))

    @app.get("/mnemonics")
    def mnemonic():
        text = current_text()
        if not text:
            return need_notes()
        from utils.mnemonics import create_mnemonics

        sets, error = run(create_mnemonics, text)
        if sets is not None and not sets:
            error = "No lists or key terms were found to build mnemonics from. Notes with bullet lists work best."
        return render_template("mnemonics.html", sets=sets or [], error=error)

    @app.get("/ppt")
    def ppt():
        text = current_text()
        if not text:
            return need_notes()
        from utils.pptgen import generate_ppt

        out, error = run(generate_ppt, text, app.config["GENERATED_DIR"])
        filename, slides = out if out else (None, 0)
        return render_template("ppt.html", filename=filename, slides=slides, error=error, stats=parse(text).stats())

    @app.route("/tts", methods=["GET", "POST"])
    def tts():
        text = current_text()
        if not text:
            return need_notes()
        from utils.tts import MAX_CHARS, speakable, text_to_speech

        doc = parse(text)
        sections = [s.title for s in doc.all_sections() if s.title]
        filename = error = spoken = None
        scope = request.form.get("scope", "summary")
        lang = request.form.get("lang", "en")
        if request.method == "POST":
            if scope not in ("summary", "full") and scope not in sections:
                scope = "summary"
            spoken = speakable(doc, scope)
            filename, error = run(text_to_speech, spoken, app.config["GENERATED_DIR"], lang)
        return render_template("tts.html", sections=sections, filename=filename, error=error, spoken=spoken, scope=scope,
                               languages=TTS_LANGUAGES, lang=lang, limit=MAX_CHARS)

    @app.route("/qna", methods=["GET", "POST"])
    def qna():
        text = current_text()
        if not text:
            return need_notes()
        results = error = None
        questions_raw = request.form.get("questions", "")
        if request.method == "POST":
            from utils.qna import get_answers

            questions = [q.strip() for q in questions_raw.splitlines() if q.strip()][:10]
            if not questions:
                error = "Type at least one question."
            else:
                results, error = run(get_answers, text, questions)
        return render_template("qna.html", results=results, error=error, questions=questions_raw)

    # ------------------------------------------------------ notebook tools
    @app.route("/sources", methods=["GET", "POST"])
    def sources():
        items = source_list()
        if not items and current_text():
            items = [srclib.make_source(srclib.default_name(current_text(), "My notes"), current_text())]
            store.update(sources=items)
        if request.method == "POST":
            action, sid = request.form.get("action"), request.form.get("id")
            if action == "toggle":
                for x in items:
                    if x["id"] == sid:
                        x["on"] = not x.get("on", True)
            elif action == "remove":
                items = [x for x in items if x["id"] != sid]
            elif action == "clear":
                items = []
            rebuild(items)
            return redirect(url_for("sources"))
        from utils.notebook import source_guide

        guides = {}
        for x in items:
            guide, _ = run(source_guide, x["text"], x["name"])
            guides[x["id"]] = guide
        return render_template("sources.html", items=items, guides=guides, max_sources=srclib.MAX_SOURCES,
                               allowed=sorted(e.lstrip(".") for e in ALLOWED_EXTENSIONS),
                               max_mb=app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024), active=sum(1 for x in items if x.get("on", True)))

    @app.route("/chat", methods=["GET", "POST"])
    def chat():
        text = current_text()
        if not text:
            return need_notes()
        from utils import chat as chatlib
        from utils.notebook import suggested_questions

        history = store.get("chat") or []
        if request.method == "POST":
            if request.form.get("action") == "clear":
                store.update(chat=[])
            else:
                question = request.form.get("question", "").strip()[:300]
                if question:
                    result, error = run(chatlib.answer, text, question, multi_sources())
                    history = (history + [result or {"q": question, "a": error, "cites": [], "also": []}])[-30:]
                    store.update(chat=history)
            return redirect(url_for("chat") + "#latest")
        return render_template("chat.html", history=history, suggestions=suggested_questions(parse(text), 6),
                               prefill=request.args.get("q", "")[:300], multi=multi_sources())

    @app.route("/audio-overview", methods=["GET", "POST"])
    def audio_overview():
        text = current_text()
        if not text:
            return need_notes()
        from utils.notebook import audio_mp3, audio_script

        length = request.values.get("length", "short")
        length = length if length in ("short", "long") else "short"
        lang = request.values.get("lang", "en")
        lang = lang if lang in TTS_LANGUAGES else "en"
        turns = audio_script(text, length)
        filename = error = None
        if request.method == "POST":
            filename, error = run(audio_mp3, turns, app.config["GENERATED_DIR"], lang)
        return render_template("audio.html", turns=turns, filename=filename, error=error, length=length, lang=lang,
                               languages=TTS_LANGUAGES)

    def make_guide(kind):
        def view():
            text = current_text()
            if not text:
                return need_notes()
            from utils import notebook as nb

            build = {"briefing": nb.briefing, "studyguide": nb.study_guide, "faq": nb.faq, "timeline": nb.timeline}[kind]
            data, error = run(build, text)
            if request.args.get("fmt") == "md" and data:
                return Response(nb.to_markdown(kind, data), mimetype="text/markdown",
                                headers={"Content-Disposition": f'attachment; filename="NoteGenius-{kind}.md"'})
            return render_template("studyguide.html", kind=kind, data=data, error=error)
        view.__name__ = kind
        return view

    for _kind in ("briefing", "studyguide", "faq", "timeline"):
        app.add_url_rule(f"/{_kind}", endpoint=_kind, view_func=make_guide(_kind))

    @app.route("/mcq", methods=["GET", "POST"])
    def mcq():
        text = current_text()
        if not text:
            return need_notes()
        quiz = store.get("quiz")

        if request.method == "POST":
            action = request.form.get("action")
            if action in ("start_quiz", "preview"):
                from utils.mcq_generator import MCQGenerator

                count = _clamp(request.form.get("count"), 8, 1, 30)
                difficulty = request.form.get("difficulty", "medium")
                if difficulty not in ("easy", "medium", "hard"):
                    difficulty = "medium"
                types = [t for t in request.form.getlist("types") if t in dict(QUIZ_TYPES)] or None
                questions, error = run(lambda: MCQGenerator().generate_from_document(parse(text), count, difficulty, types))
                if error or not questions:
                    flash(error or "No questions could be made from these notes with those settings. Try other question types or longer notes.", "error")
                    return redirect(url_for("mcq"))
                if action == "preview":
                    return render_template("mcq.html", mode="preview", questions=questions)
                store.update(quiz={"questions": questions, "current": 0, "score": 0, "answered": None, "missed": []})
            elif action == "retry_missed":
                last = store.get("last_quiz") or {}
                missed = last.get("missed") or []
                if missed:
                    store.update(quiz={"questions": missed, "current": 0, "score": 0, "answered": None, "missed": []})
                else:
                    flash("Nothing to retry.", "info")
            elif action == "submit_answer" and quiz and quiz.get("answered") is None:
                question = quiz["questions"][quiz["current"]]
                chosen = request.form.get("option", "")
                if chosen not in question["options"]:
                    flash("Choose one of the answers.", "error")
                    return redirect(url_for("mcq"))
                correct = chosen == question["answer"]
                quiz["score"] += int(correct)
                if not correct:
                    quiz["missed"].append(question)
                quiz["answered"] = {"chosen": chosen, "correct": correct}
                store.update(quiz=quiz)
            elif action == "next_question" and quiz and quiz.get("answered") is not None:
                quiz["current"] += 1
                quiz["answered"] = None
                if quiz["current"] >= len(quiz["questions"]):
                    result = {"score": quiz["score"], "total": len(quiz["questions"]), "missed": quiz["missed"]}
                    store.update(quiz=None, last_quiz=result)
                    return render_template("mcq.html", mode="result", **result)
                store.update(quiz=quiz)
            elif action == "quit":
                store.update(quiz=None)
            return redirect(url_for("mcq"))

        if quiz:
            return render_template("mcq.html", mode="quiz", quiz=quiz, question=quiz["questions"][quiz["current"]], answered=quiz["answered"])
        from utils.mcq_generator import MCQGenerator

        available = MCQGenerator().available_types(text)
        return render_template("mcq.html", mode="start", types=QUIZ_TYPES, available=available)

    @app.route("/suggestions", methods=["GET", "POST"])
    def suggestions():
        text = current_text()
        if not text:
            return need_notes()
        from utils.suggestions import fetch_videos, find_topics

        found = find_topics(text)
        videos = {}
        if request.method == "POST":
            videos, _err = run(fetch_videos, [t["name"] for t in found["topics"][:5]])
            videos = videos or {}
            if not videos:
                flash("Could not load video titles right now. The Videos buttons below still open YouTube searches.", "info")
        return render_template("suggestions.html", found=found, videos=videos)

    @app.get("/favicon.ico")
    def favicon():
        return ("", 204)

    @app.get("/files/<name>")
    def download(name):
        if not _FILE_RE.match(name):
            abort(404)
        attachment = name.endswith(".pptx")
        return send_from_directory(app.config["GENERATED_DIR"], name, as_attachment=attachment,
                                   download_name="NoteGenius-slides.pptx" if attachment else None)

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(413)
    @app.errorhandler(500)
    def error_page(err):
        code = getattr(err, "code", 500)
        messages = {
            400: getattr(err, "description", None) or "That request could not be understood.",
            404: "That page does not exist.",
            413: "That file is too large. Try a smaller file.",
            500: "Something went wrong on our side. Try again in a moment.",
        }
        return render_template("error.html", code=code, message=messages.get(code, "Something went wrong.")), code

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=_truthy(os.environ.get("FLASK_DEBUG", "0")))
