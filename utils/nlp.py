"""Shared, lazily loaded NLP resources (spaCy model and NLTK data).

Nothing heavy happens at import time, so the web app starts fast and a missing
optional resource only affects the feature that needs it.
"""
import logging
import os
from functools import lru_cache

import nltk

log = logging.getLogger(__name__)

_NLTK_PATHS = {
    "stopwords": ("corpora/stopwords", "corpora/stopwords.zip"),
    "punkt": ("tokenizers/punkt", "tokenizers/punkt.zip"),
    "punkt_tab": ("tokenizers/punkt_tab", "tokenizers/punkt_tab.zip"),
    "wordnet": ("corpora/wordnet", "corpora/wordnet.zip"),
    "omw-1.4": ("corpora/omw-1.4", "corpora/omw-1.4.zip"),
}


# NLTK data shipped inside the project, so hosts with a read-only disk (Vercel) never need to download anything.
_BUNDLED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "nltk_data")
if os.path.isdir(_BUNDLED) and _BUNDLED not in nltk.data.path:
    nltk.data.path.insert(0, _BUNDLED)


def _writable_nltk_dir():
    for d in (os.environ.get("NLTK_DATA", "").split(os.pathsep)[0], os.path.expanduser("~/nltk_data"), "/tmp/nltk_data"):
        if not d:
            continue
        try:
            os.makedirs(d, exist_ok=True)
            if os.access(d, os.W_OK):
                if d not in nltk.data.path:
                    nltk.data.path.append(d)
                return d
        except OSError:
            continue
    return None


def _has_nltk(name):
    for path in _NLTK_PATHS[name]:
        try:
            nltk.data.find(path)
            return True
        except LookupError:
            continue
    return False


@lru_cache(maxsize=None)
def ensure_nltk(*names):
    """Make sure the named NLTK packages exist, downloading any that are missing (once per process)."""
    for name in names:
        if not _has_nltk(name):
            log.info("Downloading NLTK data: %s", name)
            try:
                nltk.download(name, quiet=True, download_dir=_writable_nltk_dir())
            except Exception as exc:  # network problems must not crash the app
                log.warning("Could not download NLTK data %s: %s", name, exc)
    return True


@lru_cache(maxsize=1)
def stopword_set():
    ensure_nltk("stopwords")
    from nltk.corpus import stopwords

    return frozenset(stopwords.words("english"))


def split_sentences(text):
    """Sentence-split text with NLTK; returns a list of non-empty strings."""
    ensure_nltk("punkt_tab")
    from nltk.tokenize import sent_tokenize

    return [s.strip() for s in sent_tokenize(text) if s.strip()]
