"""Notebook features: several sources, grounded chat with citations, audio overview, briefing / study guide / FAQ / timeline."""
import html as _html
import io
import re

from conftest import MATHS, SAMPLE, token
from utils import notebook as nb, sources as so, structure as st


def post(client, path, page="/", **data):
    data["csrf_token"] = token(client, page)
    return client.post(path, data=data)


def two_sources(client):
    post(client, "/text_input", input_text=SAMPLE)
    post(client, "/text_input", page="/sources", input_text=MATHS, add="1", name="Maths notes")
    return client


def test_combined_sources_become_top_level_sections():
    doc = st.parse(so.combine([so.make_source("Physics", SAMPLE), so.make_source("Maths", MATHS)]))
    assert [s.title for s in doc.sections] == ["Physics", "Maths"]
    assert doc.formulas and all(not f.raw.startswith("@@") for f in doc.formulas)
    assert so.combine([so.make_source("One", SAMPLE)]) == SAMPLE  # one source is used as it is


def test_add_toggle_and_remove_sources(client):
    two_sources(client)
    html = client.get("/sources").get_data(as_text=True)
    assert "Maths notes" in html and "Source guide" in html and "2 of 2 on" in html
    sid = re.findall(r'name="id" value="([0-9a-f]{10})"', html)
    assert len(set(sid)) == 2
    post(client, "/sources", page="/sources", action="toggle", id=sid[0])
    assert "1 of 2 on" in client.get("/sources").get_data(as_text=True)
    assert "Quadratic" in client.get("/formulas").get_data(as_text=True)  # the maths source is still on
    post(client, "/sources", page="/sources", action="remove", id=sid[1])
    assert "0 of 1 on" in client.get("/sources").get_data(as_text=True) or "1 of 1" in client.get("/sources").get_data(as_text=True)


def test_upload_can_add_a_source(client):
    post(client, "/text_input", input_text=SAMPLE)
    data = {"csrf_token": token(client, "/sources"), "add": "1", "uploaded_file": (io.BytesIO(MATHS.encode()), "algebra_notes.txt")}
    resp = client.post("/upload_file", data=data, content_type="multipart/form-data")
    assert resp.headers["Location"].endswith("/sources")
    assert "algebra notes" in client.get("/sources").get_data(as_text=True)


def test_source_limit(client):
    post(client, "/text_input", input_text=SAMPLE)
    for i in range(14):
        post(client, "/text_input", page="/sources", input_text=f"Extra source number {i} with enough text to be accepted.", add="1")
    assert client.get("/sources").get_data(as_text=True).count('class="srccard') == so.MAX_SOURCES


def test_chat_answers_from_sources_with_citations(client):
    two_sources(client)
    post(client, "/chat", page="/chat", question="What is the quadratic formula?")
    post(client, "/chat", page="/chat", question="Who won the football world cup in 1998?")
    html = _html.unescape(client.get("/chat").get_data(as_text=True))
    assert "What is the quadratic formula?" in html and 'class="cite"' in html
    assert "Maths notes › Algebra" in html  # the citation names the source and section
    assert "couldn't find that in your sources" in html
    post(client, "/chat", page="/chat", action="clear")
    assert "No questions yet" in client.get("/chat").get_data(as_text=True)


def test_chat_history_resets_when_sources_change(client):
    two_sources(client)
    post(client, "/chat", page="/chat", question="Tell me about zebra migration patterns")
    assert "zebra migration" in client.get("/chat").get_data(as_text=True)
    post(client, "/text_input", input_text=SAMPLE)
    assert "zebra migration" not in client.get("/chat").get_data(as_text=True)


def test_audio_script_is_grounded_and_has_two_hosts():
    turns = nb.audio_script(SAMPLE, "short")
    assert {t["name"] for t in turns} == {"Alex", "Sam"} and len(turns) >= 6
    spoken = " ".join(t["text"] for t in turns).lower()
    assert "motion" in spoken and "velocity" in spoken
    assert len(nb.audio_script(SAMPLE, "long")) >= len(turns)


def test_audio_overview_page_and_mp3(client, monkeypatch):
    post(client, "/text_input", input_text=SAMPLE)
    html = client.get("/audio-overview").get_data(as_text=True)
    assert "Listen in your browser" in html and 'class="turn a"' in html and 'class="turn b"' in html
    calls = []

    class FakeTTS:
        def __init__(self, text, lang="en", tld="com", **kw):
            calls.append((tld, lang))

        def write_to_fp(self, fp):
            fp.write(b"ID3fake")

    import gtts
    monkeypatch.setattr(gtts, "gTTS", FakeTTS)
    html = post(client, "/audio-overview", page="/audio-overview", length="short", lang="en").get_data(as_text=True)
    assert "Download MP3" in html and {"com", "co.uk"} <= {c[0] for c in calls}


def test_audio_mp3_failure_is_explained(client, monkeypatch):
    post(client, "/text_input", input_text=SAMPLE)

    class Boom:
        def __init__(self, *a, **k):
            raise OSError("offline")

    import gtts
    monkeypatch.setattr(gtts, "gTTS", Boom)
    html = post(client, "/audio-overview", page="/audio-overview", length="short", lang="en").get_data(as_text=True)
    assert "could not be reached" in html and 'class="turn' in html  # the transcript is still there


def test_guides_render_and_export(client):
    two_sources(client)
    for path, needle in (("/briefing", "Key terms"), ("/studyguide", "Answer key"), ("/faq", "What is"), ("/timeline", "Timeline")):
        resp = client.get(path)
        assert resp.status_code == 200 and needle in resp.get_data(as_text=True), path
    for kind in ("briefing", "studyguide", "faq"):
        md = client.get(f"/{kind}?fmt=md")
        assert md.status_code == 200 and md.mimetype == "text/markdown" and md.get_data(as_text=True).startswith("# ")


def test_timeline_finds_dated_events():
    ev = nb.timeline("# History\n\nThe printing press was invented in 1440 by Gutenberg.\n\nThe revolution began in 1789 and changed politics.")["events"]
    assert [e["year"] for e in ev] == [1440, 1789]
    assert nb.timeline(SAMPLE)["events"] == [] or all(e["year"] > 1000 for e in nb.timeline(SAMPLE)["events"])


def test_study_guide_has_questions_with_answers():
    g = nb.study_guide(SAMPLE)
    assert g["short"] and all(q["q"] and q["a"] for q in g["short"]) and g["glossary"]


def test_notebook_tools_listed_and_need_notes(client):
    for path in ("/chat", "/audio-overview", "/briefing", "/studyguide", "/faq", "/timeline"):
        assert client.get(path).status_code == 302, path
    post(client, "/text_input", input_text=SAMPLE)
    html = client.get("/operations").get_data(as_text=True)
    for name in ("Chat with your notes", "Audio overview", "Briefing doc", "Study guide", "FAQ", "Timeline", "Sources"):
        assert name in html
