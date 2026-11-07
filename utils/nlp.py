"""Shared, lazily loaded NLP resources (spaCy model and NLTK data).

Nothing heavy happens at import time, so the web app starts fast and a missing
optional resource only affects the feature that needs it.
"""
import logging
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
                nltk.download(name, quiet=True)
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
    ensure_nltk("punkt", "punkt_tab")
    from nltk.tokenize import sent_tokenize

    return [s.strip() for s in sent_tokenize(text) if s.strip()]
