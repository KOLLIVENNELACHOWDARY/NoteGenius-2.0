"""Mnemonics: acronyms from the notes' own lists, plus a memory sentence of easy-to-picture words."""
import random
import re
from collections import Counter

from . import formulas as fx
from .nlp import stopword_set
from .structure import Document, parse

easy_words = {
    "A": ["apple", "ant", "arm", "arrow", "animal", "art", "air", "axe", "aeroplane", "anchor"],
    "B": ["ball", "bat", "bag", "bee", "bird", "boat", "book", "box", "bread", "bowl", "brush", "bus"],
    "C": ["cat", "car", "cup", "cap", "cow", "cake", "coin", "coat", "cane", "candle", "clock", "cloud"],
    "D": ["dog", "door", "duck", "doll", "drum", "dish", "dust", "desk", "dive", "dawn", "donkey", "dragon"],
    "E": ["egg", "ear", "eye", "edge", "east", "echo", "eagle", "earth", "elephant", "engine", "elbow"],
    "F": ["fan", "fish", "fig", "fog", "fox", "frog", "fun", "fire", "fork", "fence", "foot", "farm", "flag"],
    "G": ["gap", "gem", "goat", "girl", "gold", "game", "gift", "golf", "gown", "grape", "grass", "glue"],
    "H": ["hat", "hen", "hop", "hot", "hut", "hill", "hand", "home", "hive", "honey", "hair", "heart"],
    "I": ["ink", "ice", "ivy", "iron", "idea", "inch", "island", "igloo", "insect", "image"],
    "J": ["jam", "jar", "jet", "job", "joy", "jug", "jog", "joke", "jewel", "jump", "jungle", "juice"],
    "K": ["key", "kit", "kid", "kite", "king", "kick", "knee", "knot", "knock", "kitchen", "koala"],
    "L": ["lip", "log", "leg", "lid", "lap", "lamp", "leaf", "line", "lamb", "lake", "lion", "lemon"],
    "M": ["man", "map", "mat", "mix", "mud", "milk", "moon", "mail", "mop", "mug", "mask", "mouse"],
    "N": ["net", "nap", "nut", "nail", "name", "nose", "nest", "night", "note", "nurse", "noodle"],
    "O": ["owl", "oil", "oak", "open", "ox", "one", "oven", "ocean", "orange", "orbit", "onion"],
    "P": ["pen", "pig", "pot", "pan", "pet", "pin", "pie", "pack", "park", "palm", "page", "piano", "pizza"],
    "Q": ["queen", "quiz", "quill", "quick", "quiet", "quest", "quilt", "quote", "quail"],
    "R": ["rat", "rug", "run", "row", "red", "rice", "rock", "ring", "road", "rain", "rose", "rabbit"],
    "S": ["sun", "sea", "sit", "saw", "sock", "sand", "seal", "star", "stick", "stone", "snake", "spoon"],
    "T": ["top", "tip", "tap", "toy", "tin", "ten", "toe", "time", "tree", "tape", "tank", "tiger", "train"],
    "U": ["urn", "up", "unit", "umbrella", "unicorn", "uncle", "uniform", "under"],
    "V": ["van", "vet", "vine", "view", "vote", "vase", "violin", "village", "video", "volcano"],
    "W": ["wet", "win", "war", "way", "web", "wax", "wood", "wish", "wall", "wave", "wool", "whale"],
    "X": ["x-ray", "xylophone", "xenon", "xerox"],
    "Y": ["yam", "yes", "yarn", "yoga", "yard", "yell", "year", "yolk", "youth", "yacht", "yak"],
    "Z": ["zip", "zoo", "zap", "zen", "zone", "zero", "zoom", "zest", "zinc", "zebra"],
}
_SKIP_START = {"the", "a", "an", "of", "and", "to", "in", "on", "for", "its", "their", "with"}


def _initial(item):
    for w in re.findall(r"[A-Za-z]+", item):
        if w.lower() not in _SKIP_START:
            return w[0].upper()
    return ""


def _memory_words(initials, rng):
    return [rng.choice(easy_words[c]).capitalize() if c in easy_words else c for c in initials]


def _pronounceable(letters):
    s = "".join(letters)
    return bool(re.search(r"[AEIOU]", s)) and not re.search(r"[^AEIOU]{4}", s)


def create_mnemonics(text, max_sets=6, seed=None):
    """Mnemonic sets from lists (acronym of the items) and from the most important terms."""
    rng = random.Random(seed)
    doc = parse(text)
    sets = []
    for sec, b in doc.lists:
        items = [i for i in b["items"] if not fx.looks_like_equation(i)]
        if not 3 <= len(items) <= 9:
            continue
        initials = [_initial(i) for i in items]
        if not all(initials):
            continue
        title = b.get("label") or sec.title
        sets.append({
            "title": title, "source": "list", "acronym": "".join(initials),
            "acronym_ok": _pronounceable(initials), "words": _memory_words(initials, rng),
            "pairs": [(i if len(i) < 70 else i[:67] + "…", c, w) for i, c, w in zip(items, initials, _memory_words(initials, rng))],
        })
        sets[-1]["sentence"] = " ".join(sets[-1]["words"])
        if len(sets) >= max_sets:
            return sets
    stop = stopword_set()
    pool = [d.term for d in doc.definitions]
    if len(pool) < 4:
        counts = Counter(w for w in re.findall(r"[A-Za-z]{5,}", text.lower()) if w not in stop)
        pool += [w for w, _ in counts.most_common(12)]
    per_section = {}
    for d in doc.definitions:
        per_section.setdefault(d.section, []).append(d.term)
    groups = [(sec, terms[:6]) for sec, terms in per_section.items() if len(terms) >= 3]
    if not groups and len(pool) >= 3:
        groups = [("Key terms", pool[:6])]
    for sec, terms in groups:
        if len(sets) >= max_sets:
            break
        initials = [_initial(t) for t in terms]
        words = _memory_words(initials, rng)
        sets.append({"title": f"Key terms: {sec}" if sec != "Key terms" else "Key terms", "source": "terms", "acronym": "".join(initials),
                     "acronym_ok": _pronounceable(initials), "words": words, "sentence": " ".join(words),
                     "pairs": list(zip(terms, initials, words))})
    return sets
