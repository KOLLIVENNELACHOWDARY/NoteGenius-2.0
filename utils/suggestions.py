"""Study resource suggestions: YouTube videos and (optionally) Google Custom Search results."""
import logging
import os
import re
from urllib.parse import quote_plus

from .nlp import ensure_nltk

log = logging.getLogger(__name__)


def _keywords(text, top_n=5):
    try:
        ensure_nltk("stopwords", "punkt", "punkt_tab")
        from rake_nltk import Rake

        rake = Rake(max_length=3)
        rake.extract_keywords_from_text(text)
        phrases = [p for p in rake.get_ranked_phrases() if len(p) > 3][:top_n]
        if phrases:
            return phrases
    except Exception as exc:
        log.warning("RAKE failed, using TF-IDF: %s", exc)

    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english")
    scores = vectorizer.fit_transform([text]).toarray()[0]
    names = np.array(vectorizer.get_feature_names_out())
    return names[scores.argsort()[-top_n:][::-1]].tolist()


_GENERIC_TITLES = {"introduction", "overview", "summary", "conclusion", "notes", "contents", "example", "examples", "exercise",
                   "exercises", "references", "questions", "important", "remember", "definition", "definitions", "formulas",
                   "formula", "key points", "revision", "unit", "chapter", "topic", "topics", "diagram", "table", "code"}


def topic_links(topic, subject=""):
    """Plain search links for one topic. They always work: nothing is fetched from the internet by the server."""
    q = quote_plus((topic + " " + subject).strip() if subject and subject.lower() not in topic.lower() else topic)
    return [
        ("Videos", f"https://www.youtube.com/results?search_query={q}+explained"),
        ("Wikipedia", f"https://en.wikipedia.org/wiki/Special:Search?search={quote_plus(topic)}"),
        ("Khan Academy", f"https://www.khanacademy.org/search?page_search_query={quote_plus(topic)}"),
        ("Diagrams", f"https://www.google.com/search?tbm=isch&q={q}+diagram"),
        ("Practice questions", f"https://www.google.com/search?q={q}+practice+questions+with+answers"),
        ("Google", f"https://www.google.com/search?q={q}"),
    ]


def find_topics(text, limit=8):
    """The topics worth looking up: section headings first, then defined terms. Returns [{'name', 'kind', 'links'}]."""
    from .structure import parse

    doc = parse(text)
    subject = ""
    if doc.title and len(doc.title.split()) <= 5 and doc.title.lower() not in _GENERIC_TITLES and "notes" not in doc.title.lower():
        subject = doc.title
    seen, topics = set(), []

    def add(name, kind):
        name = re.sub(r"^[\d.\s)]+", "", (name or "")).strip(" :-–—.")
        key = name.lower()
        if len(name) < 3 or len(name.split()) > 6 or key in seen or key in _GENERIC_TITLES or key == (doc.title or "").lower():
            return
        seen.add(key)
        topics.append({"name": name, "kind": kind})

    for sec in doc.all_sections():
        if sec.level >= 1:
            add(sec.title, "section")
    for d in doc.definitions:
        add(d.term, "term")
    for f in doc.formulas:
        add(f.name, "formula")
    if not topics:
        for kw in _keywords(text, 6):
            add(kw, "keyword")
    topics = topics[:limit]
    for t in topics:
        t["links"] = topic_links(t["name"], subject)
    return {"subject": subject, "topics": topics}


def fetch_videos(topics, per_topic=3):
    """Try to read the top YouTube results for each topic. Returns {topic: [(title, url)]}; empty when YouTube cannot be reached."""
    out = {}
    try:
        from youtube_search import YoutubeSearch
    except Exception:
        return out
    for name in topics:
        try:
            vids = []
            for item in YoutubeSearch(name + " explained", max_results=per_topic + 2).to_dict():
                suffix = item.get("url_suffix") or ""
                if suffix.startswith("/watch"):
                    vids.append((item.get("title", "Untitled"), "https://www.youtube.com" + suffix))
            if vids:
                out[name] = vids[:per_topic]
        except Exception as exc:
            log.warning("YouTube search failed for %s: %s", name, exc)
            break
    return out


def suggest_links(text, google_api_key=None, google_cse_id=None):
    """Return keywords, a search query, Google results, YouTube videos and plain search links."""
    keywords = _keywords(text)
    query = " ".join(keywords[:3]) if keywords else text[:100]

    google = {"links": [], "error": None}
    if google_api_key and google_cse_id:
        try:
            import requests

            resp = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={"key": google_api_key, "cx": google_cse_id, "q": query, "num": 5},
                timeout=10,
            )
            data = resp.json()
            if "error" in data:
                google["error"] = "Google search returned an error. Check the API key and search engine id."
            else:
                google["links"] = [
                    (item.get("title", item["link"]), item["link"]) for item in data.get("items", []) if item.get("link")
                ]
        except Exception as exc:
            log.warning("Google search failed: %s", exc)
            google["error"] = "Google search could not be reached."
    else:
        google["error"] = "Google results are off. Set GOOGLE_API_KEY and GOOGLE_CSE_ID to turn them on."

    videos = []
    try:
        from youtube_search import YoutubeSearch

        for item in YoutubeSearch(query, max_results=5).to_dict():
            suffix = item.get("url_suffix") or ""
            if suffix.startswith("/watch"):
                videos.append((item.get("title", "Untitled"), "https://www.youtube.com" + suffix))
    except Exception as exc:
        log.warning("YouTube search failed: %s", exc)

    encoded = quote_plus(query)
    return {
        "keywords": keywords,
        "query": query,
        "google": google,
        "youtube": videos,
        "search_links": [
            ("Search YouTube", f"https://www.youtube.com/results?search_query={encoded}"),
            ("Search Google", f"https://www.google.com/search?q={encoded}"),
        ],
    }
