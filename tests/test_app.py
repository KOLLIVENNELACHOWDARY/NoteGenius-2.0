import html as _html
import io
import re

from conftest import MATHS, SAMPLE, token


def post(client, path, page="/", **data):
    data["csrf_token"] = token(client, page)
    return client.post(path, data=data)


# ----------------------------------------------------------------- basics
def test_health_and_home(client):
    assert client.get("/healthz").get_json() == {"status": "ok"}
    html = client.get("/").get_data(as_text=True)
    assert "Paste your notes" in html and "Upload a file" in html and "katex.min.js" in html


def test_security_headers(client):
    resp = client.get("/")
    csp = resp.headers["Content-Security-Policy"]
    assert resp.headers["X-Content-Type-Options"] == "nosniff" and "script-src 'self'" in csp and "unsafe-eval" not in csp


def test_katex_assets_are_served_locally(client):
    assert client.get("/static/vendor/katex/katex.min.js").status_code == 200
    assert client.get("/static/vendor/katex/fonts/KaTeX_Main-Regular.woff2").status_code == 200
    assert "cdn" not in client.get("/").get_data(as_text=True)


def test_post_without_csrf_is_rejected(client):
    assert client.post("/text_input", data={"input_text": SAMPLE}).status_code == 400


def test_every_tool_redirects_home_without_notes(client):
    for path in ("/operations", "/overview", "/summary", "/flashcards", "/flashcards.csv", "/formulas", "/glossary", "/cheatsheet",
                 "/studyplan", "/mindmap", "/mnemonics", "/ppt", "/tts", "/qna", "/qgen", "/mcq", "/summary.md"):
        resp = client.get(path)
        assert resp.status_code == 302 and resp.headers["Location"].endswith("/"), path


def test_short_text_rejected(client):
    assert post(client, "/text_input", input_text="hi").headers["Location"].endswith("/")
    assert client.get("/operations").status_code == 302


def test_large_notes_survive_beyond_cookie_limit(client):
    assert post(client, "/text_input", input_text=(SAMPLE + "\n\n") * 8).status_code == 302
    assert "Choose what you want to make" in client.get("/operations").get_data(as_text=True)


def test_operations_lists_every_tool_and_counts(loaded):
    html = loaded.get("/operations").get_data(as_text=True)
    for name in ("Notes overview", "Summary", "Mind maps", "Slides", "Flashcards", "Formula sheet", "Glossary", "Mnemonics", "Listen",
                 "Multiple-choice quiz", "Practice questions", "Ask your notes", "Study plan", "Cheat sheet", "Study resources"):
        assert name in html
    assert "<strong>8</strong> formulas" in html and "<strong>2</strong> tables" in html


# ----------------------------------------------------- pages show real maths
def test_formula_sheet_carries_latex_for_the_browser(loaded):
    html = loaded.get("/formulas").get_data(as_text=True)
    assert 'data-tex="F = ma"' in html and "Newton&#39;s second law" in html
    assert "final velocity" in html and "\\frac{1}{2} m v^{2}" in html


def test_overview_lists_tables_formulas_and_allows_editing(loaded):
    html = loaded.get("/overview").get_data(as_text=True)
    assert "<th scope=\"col\">SI Unit</th>" in html and "Equations of motion" in html
    resp = post(loaded, "/overview", page="/overview", text="# New\n\nForce is a push or pull on an object.\nF = ma")
    assert resp.status_code == 302
    assert "New" in loaded.get("/overview").get_data(as_text=True)


def test_summary_levels_and_markdown_download(loaded):
    for level in ("brief", "standard", "detailed"):
        assert loaded.get(f"/summary?level={level}").status_code == 200
    resp = loaded.get("/summary.md")
    assert resp.mimetype == "text/markdown" and b"`F = ma`" in resp.data


def test_glossary_cheatsheet_and_mnemonics(loaded):
    assert "Kinetic energy" in loaded.get("/glossary").get_data(as_text=True)
    assert "Formulas" in loaded.get("/cheatsheet").get_data(as_text=True)
    assert "KPT" in loaded.get("/mnemonics").get_data(as_text=True)


def test_flashcards_page_and_csv(loaded):
    html = loaded.get("/flashcards").get_data(as_text=True)
    assert 'id="deck-data"' in html and "flashcards.js" in html
    csv = loaded.get("/flashcards.csv")
    assert csv.mimetype == "text/csv" and b"Front,Back,Tags" in csv.data


def test_flashcard_json_cannot_break_out_of_the_page(client):
    evil = "# Test\n\nBad term is defined as </script><script>alert(1)</script> text here.\nF = ma"
    post(client, "/text_input", input_text=evil)
    assert "</script><script>alert" not in client.get("/flashcards").get_data(as_text=True)


def test_mindmap_page_is_one_interactive_tree_and_picture_is_on_demand(loaded):
    html = loaded.get("/mindmap").get_data(as_text=True)
    assert 'class="mm-viewport"' in html and "mm-section" in html and "Fit to screen" in html
    assert "<img" not in html.split('id="mm-viewport"')[1].split("</ul>\n<ul class=\"legend\"")[0]
    resp = loaded.get("/mindmap/image")
    assert resp.status_code == 302 and "/files/mindmap_" in resp.headers["Location"]
    png = loaded.get(resp.headers["Location"])
    assert png.status_code == 200 and png.data[:4] == b"\x89PNG"


def test_slides_download(loaded):
    html = loaded.get("/ppt").get_data(as_text=True)
    name = re.search(r"/files/(slides_[0-9a-f]{32}\.pptx)", html).group(1)
    resp = loaded.get(f"/files/{name}")
    assert resp.status_code == 200 and resp.data[:2] == b"PK" and "attachment" in resp.headers["Content-Disposition"]


def test_qna(loaded, monkeypatch):
    monkeypatch.setenv("QA_BACKEND", "search")
    html = post(loaded, "/qna", page="/qna", questions="formula for kinetic energy\ndefine speed").get_data(as_text=True)
    assert "KE = \\frac{1}{2} m v^{2}" in html and "distance travelled" in html
    assert "Type at least one question" in post(loaded, "/qna", page="/qna", questions="  ").get_data(as_text=True)


def test_practice_questions(loaded):
    html = post(loaded, "/qgen", page="/qgen", num_questions="6").get_data(as_text=True)
    assert "Model answer" in html and "marks" in html


def test_study_plan_with_days_and_with_exam_date(loaded):
    html = post(loaded, "/studyplan", page="/studyplan", days="4", minutes="45").get_data(as_text=True)
    assert "Final check" in html and "Learn" in html and html.count("<tr>") >= 5
    assert "future" in post(loaded, "/studyplan", page="/studyplan", exam="2020-01-01", days="3", minutes="30").get_data(as_text=True)


def test_tts_reads_formulas_in_words(loaded, monkeypatch):
    import gtts

    seen = {}

    class Fake:
        def __init__(self, text, lang, slow):
            seen["text"], seen["lang"] = text, lang

        def save(self, path):
            open(path, "wb").write(b"ID3fake")

    monkeypatch.setattr(gtts, "gTTS", Fake)
    html = post(loaded, "/tts", page="/tts", scope="full", lang="hi").get_data(as_text=True)
    assert "speech_" in html and seen["lang"] == "hi" and "v equals u plus a t" in seen["text"]
    assert "Unsupported language" in post(loaded, "/tts", page="/tts", scope="summary", lang="xx").get_data(as_text=True)


def test_suggestions_shows_a_card_per_topic_with_working_links(loaded):
    html = loaded.get("/suggestions").get_data(as_text=True)
    assert "rcard" in html and "youtube.com/results?search_query=" in html and "wikipedia.org" in html
    assert "Motion" in html
    # the POST (video titles) must also render, even when YouTube cannot be reached
    assert "rcard" in post(loaded, "/suggestions", page="/suggestions").get_data(as_text=True)


# -------------------------------------------------------------------- quiz
def _answer_all(client, pick_correct):
    seen, result = 0, None
    while seen < 40:
        html = client.get("/mcq").get_data(as_text=True)
        if "Check answer" not in html:
            break
        options = [_html.unescape(o) for o in re.findall(r'name="option" value="([^"]+)"', html)]
        assert len(options) >= 3
        choice = options[0]
        if pick_correct:
            post(client, "/mcq", page="/mcq", action="submit_answer", option=choice)
            html = client.get("/mcq").get_data(as_text=True)
            answer = re.search(r"The answer is (.+?)\.<", html)
        else:
            post(client, "/mcq", page="/mcq", action="submit_answer", option=choice)
        result = post(client, "/mcq", page="/mcq", action="next_question")
        seen += 1
        if "Quiz complete" in result.get_data(as_text=True):
            return result.get_data(as_text=True)
    return result.get_data(as_text=True) if result else ""


def test_quiz_flow_shows_review_and_retries_missed(loaded):
    post(loaded, "/mcq", page="/mcq", action="start_quiz", count="6", difficulty="easy", types=["definition", "formula", "symbol", "table"])
    html = _answer_all(loaded, False)
    assert "Quiz complete" in html
    if "Retry the" in html:
        assert "Review what you missed" in html
        post(loaded, "/mcq", page="/mcq", action="retry_missed")
        assert "Question 1 of" in loaded.get("/mcq").get_data(as_text=True)


def test_quiz_formula_options_are_typeset(loaded):
    post(loaded, "/mcq", page="/mcq", action="start_quiz", count="1", difficulty="easy", types=["formula"])
    html = loaded.get("/mcq").get_data(as_text=True)
    assert 'class="tex"' in html and "Which formula gives" in html


def test_quiz_type_filter_and_forged_option(loaded):
    post(loaded, "/mcq", page="/mcq", action="start_quiz", count="3", difficulty="easy", types=["table"])
    assert "From the table" in loaded.get("/mcq").get_data(as_text=True)
    post(loaded, "/mcq", page="/mcq", action="submit_answer", option="not-an-option")
    assert "Check answer" in loaded.get("/mcq").get_data(as_text=True)


def test_quiz_preview(loaded):
    html = post(loaded, "/mcq", page="/mcq", action="preview", count="4", difficulty="easy").get_data(as_text=True)
    assert "Quiz preview" in html and "(answer)" in html


# ----------------------------------------------------------------- uploads
def _upload(client, name, data):
    return client.post("/upload_file", data={"csrf_token": token(client), "uploaded_file": (io.BytesIO(data), name)},
                       content_type="multipart/form-data")


def test_upload_txt_md_and_maths_notes(client):
    assert _upload(client, "notes.txt", SAMPLE.encode()).headers["Location"].endswith("/operations")
    assert _upload(client, "notes.md", MATHS.encode()).headers["Location"].endswith("/operations")
    assert "Quadratic formula" in client.get("/formulas").get_data(as_text=True)


def test_upload_docx_and_pdf_keep_structure(client, tmp_path):
    from test_extract import make_docx, make_pdf

    for maker, name in ((make_docx, "n.docx"), (make_pdf, "n.pdf")):
        path = str(tmp_path / name)
        maker(path)
        assert _upload(client, name, open(path, "rb").read()).headers["Location"].endswith("/operations")
        html = client.get("/overview").get_data(as_text=True)
        assert "<th scope=\"col\">" in html  # a table was detected


def test_upload_rejects_bad_type_and_cleans_up(client, app):
    resp = _upload(client, "evil.exe", b"MZ")
    assert not resp.headers["Location"].endswith("operations")
    assert _upload(client, "../../etc/passwd.txt", SAMPLE.encode()).headers["Location"].endswith("/operations")
    import os

    assert os.listdir(app.config["UPLOAD_DIR"]) == []


def test_upload_corrupt_pdf_gives_message(client):
    assert _upload(client, "broken.pdf", b"not a pdf").status_code == 302
    assert "could not be read" in client.get("/").get_data(as_text=True)


def test_upload_too_large(app):
    app.config["MAX_CONTENT_LENGTH"] = 1024
    assert _upload(app.test_client(), "big.txt", b"x" * 5000).status_code == 413


def test_download_only_serves_generated_names(client, app):
    open(f"{app.config['GENERATED_DIR']}/secret.txt", "w").write("x")
    for bad in ("secret.txt", "..%2Fapp.py", "slides_x.pptx", "mindmap_" + "g" * 32 + ".png"):
        assert client.get(f"/files/{bad}").status_code == 404, bad


# -------------------------------------------------- any kind of input works
def test_plain_prose_without_any_markup(client):
    prose = ("Photosynthesis is the process by which green plants make food using sunlight. Chlorophyll absorbs light energy. "
             "Water and carbon dioxide are converted into glucose and oxygen. This process takes place in the chloroplasts of leaf cells.")
    post(client, "/text_input", input_text=prose)
    for path in ("/summary", "/flashcards", "/mindmap", "/ppt", "/mcq", "/qgen", "/cheatsheet", "/glossary", "/formulas", "/overview"):
        assert client.get(path).status_code == 200, path


def test_messy_input_never_crashes_a_tool(client):
    messy = "|||\n\n\t\t\n# \n- \n$$ $$\n=\n= = =\n\x00\n" + "word " * 50
    post(client, "/text_input", input_text=messy)
    for path in ("/overview", "/summary", "/flashcards", "/formulas", "/glossary", "/cheatsheet", "/mindmap", "/ppt", "/mnemonics", "/qgen", "/mcq", "/studyplan"):
        assert client.get(path).status_code in (200, 302), path


# ------------------------------------------ safe behind a CDN / reverse proxy
def test_pages_are_never_cacheable_but_static_files_are(loaded):
    for path in ("/", "/operations", "/flashcards", "/formulas", "/healthz"):
        assert loaded.get(path).headers["Cache-Control"] == "private, no-store", path
    assert "max-age" in loaded.get("/static/css/style.css").headers["Cache-Control"]
    html = loaded.get("/ppt").get_data(as_text=True)
    name = re.search(r"/files/(slides_[0-9a-f]{32}\.pptx)", html).group(1)
    assert loaded.get(f"/files/{name}").headers["Cache-Control"] == "private, no-store"


def test_session_cookie_is_host_only_and_secure_when_configured(tmp_path):
    from app import create_app

    app = create_app({"TESTING": True, "DATA_DIR": str(tmp_path), "SECRET_KEY": "k", "SESSION_COOKIE_SECURE": True})
    c = app.test_client()
    base = "https://example.vercel.app"
    html = c.get("/", base_url=base).get_data(as_text=True)
    tok = re.search(r'name="csrf_token" value="([0-9a-f]+)"', html).group(1)
    resp = c.post("/text_input", data={"input_text": "x" * 40, "csrf_token": tok}, base_url=base)
    assert resp.status_code == 302
    set_cookie = " ".join(resp.headers.getlist("Set-Cookie"))
    assert "Secure" in set_cookie and "HttpOnly" in set_cookie and "SameSite=Lax" in set_cookie and "Domain=" not in set_cookie
    assert resp.headers["Location"].startswith("/")  # relative redirects keep working behind a proxy
