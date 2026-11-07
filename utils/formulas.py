"""Formula handling: find equations in plain text, convert them to LaTeX, read them aloud, draw them as images.

Works on plain-text notes ("v = u + at", "E = mc^2", "x²+y²=r²", "sqrt(b^2 - 4ac)"),
LaTeX ($\\frac{a}{b}$) and Unicode maths. Everything is heuristic and fails soft: if a
line cannot be converted, the original text is shown instead.
"""
import hashlib
import os
import re
import threading

from . import code as _code

GREEK = {
    "α": "alpha", "β": "beta", "γ": "gamma", "δ": "delta", "ε": "epsilon", "ζ": "zeta", "η": "eta",
    "θ": "theta", "λ": "lambda", "μ": "mu", "ν": "nu", "ξ": "xi", "π": "pi", "ρ": "rho", "σ": "sigma",
    "τ": "tau", "φ": "phi", "χ": "chi", "ψ": "psi", "ω": "omega", "Γ": "Gamma", "Δ": "Delta",
    "Θ": "Theta", "Λ": "Lambda", "Ξ": "Xi", "Π": "Pi", "Σ": "Sigma", "Φ": "Phi", "Ψ": "Psi", "Ω": "Omega",
    "ϕ": "phi", "ϵ": "epsilon", "µ": "mu",
}
GREEK_WORDS = {
    "alpha", "beta", "gamma", "delta", "epsilon", "theta", "lambda", "mu", "pi", "rho", "sigma", "tau",
    "phi", "omega", "Delta", "Sigma", "Omega", "Gamma", "Theta", "Lambda", "Phi", "Psi", "Pi",
}
SYMBOLS = {
    "×": r" \times ", "÷": r" \div ", "·": r" \cdot ", "⋅": r" \cdot ", "∙": r" \cdot ", "−": "-", "—": "-", "–": "-",
    "≤": r" \le ", "≥": r" \ge ", "⩽": r" \le ", "⩾": r" \ge ", "≠": r" \ne ", "≈": r" \approx ", "≃": r" \approx ",
    "∞": r"\infty ", "±": r" \pm ", "∓": r" \mp ", "→": r" \rightarrow ", "⟶": r" \rightarrow ",
    "⇒": r" \Rightarrow ", "⇌": r" \rightleftharpoons ", "↔": r" \leftrightarrow ", "∑": r"\sum ", "∫": r"\int ",
    "∏": r"\prod ", "∂": r"\partial ", "∇": r"\nabla ", "∝": r" \propto ", "°": r"^{\circ}", "′": "'",
    "∈": r" \in ", "∪": r" \cup ", "∩": r" \cap ", "⊂": r" \subset ", "∴": r" \therefore ", "≡": r" \equiv ",
    "≪": r" \ll ", "≫": r" \gg ", "∀": r" \forall ", "∃": r" \exists ", "%": r"\%", "…": r"\ldots ", "ℏ": r"\hbar ",
}
SUP = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻ⁿⁱ", "0123456789+-ni"))
SUB = dict(zip("₀₁₂₃₄₅₆₇₈₉₊₋ₙₓₐₑₒ", "0123456789+-nxaeo"))
FUNCS = {
    "sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "exp", "lim", "max", "min", "arcsin", "arccos",
    "arctan", "sinh", "cosh", "tanh", "det", "sup", "inf", "gcd",
}
STOP_IN_EQ = {
    "is", "are", "the", "that", "which", "this", "these", "those", "will", "can", "be", "because", "when", "if",
    "then", "so", "as", "it", "its", "was", "were", "has", "have", "hence", "thus", "therefore", "where", "also",
    "should", "must", "may", "would", "could", "but", "or", "not", "than", "with", "from", "into", "means",
}
STOP_IN_LHS = STOP_IN_EQ - {"of", "per"}
_REL = re.compile(r"(=|\\le\b|\\ge\b|\\ne\b|\\approx|\\propto|\\rightarrow|\\rightleftharpoons)")


# ---------------------------------------------------------------- detection
def has_latex(s):
    return bool(re.search(r"\$|\\(frac|sqrt|sum|int|alpha|beta|theta|pi|Delta|cdot|times|lim|vec|hat|left|begin)\b", s))


def _non_latin_words(s):
    """How many letters or marks belong to scripts other than Latin or Greek (Telugu, Devanagari, Arabic, CJK ...).
    Prose in those languages must not be mistaken for a formula."""
    import unicodedata

    n = 0
    for ch in s:
        o = ord(ch)
        if o > 0x24F and not 0x370 <= o <= 0x3FF and not 0x1F00 <= o <= 0x1FFF and not 0x2100 <= o <= 0x214F \
                and unicodedata.category(ch)[0] in "LM":
            n += 1
    return n


def looks_like_equation(s):
    """True if a line/segment is most likely a formula rather than a sentence."""
    s = s.strip()
    if not 3 <= len(s) <= 150 or s.endswith(":") or "http" in s or "@" in s:
        return False
    if has_latex(s):
        return True
    if _non_latin_words(s) >= 4:
        return False  # a sentence in Telugu, Hindi, Arabic ... is prose, not a formula
    if _code.line_score(s) >= 2:
        return False  # a program statement, not a formula
    if re.search(r"->|→|⇌|<=>", s) and _is_chem(s):
        return True
    if "=" not in s:
        return bool(re.search(r"[∑∫√∂∇∝]", s)) and len(re.findall(r"[A-Za-z]{4,}", s)) <= 3
    lhs, _, rhs = s.partition("=")
    lhs, rhs = lhs.strip(), rhs.strip().rstrip(".;,")
    if not lhs or not rhs or rhs.startswith("="):
        return False
    word = r"(?<![A-Za-z0-9])[A-Za-z]+(?![A-Za-z0-9])"
    lw = re.findall(word, lhs)
    rw = re.findall(word, rhs)
    if len(lw) > 5 or len(rw) > 10 or any(w.lower() in STOP_IN_LHS for w in lw):
        return False
    if any(w.lower() in STOP_IN_EQ for w in rw):
        return False
    long_rw = [w for w in rw if len(w) >= 4 and w not in FUNCS and w not in GREEK_WORDS]
    if len(long_rw) > 3 and not (len(lw) <= 3 and len(rw) <= 8 and re.search(r"\s[+\-×÷*/]\s", rhs) and all(w[0].isupper() for w in rw if len(w) > 2)):
        return False
    if len(s.split()) > 8 and s.endswith("."):
        return False
    if re.fullmatch(r"[a-z]{4,}", rhs) and rhs not in FUNCS and rhs not in GREEK_WORDS:
        return False  # "v = final": a symbol legend, not an equation
    if len(lw) == 1 and len(rw) == 1 and len(lw[0]) >= 4 and len(rw[0]) >= 4 and re.fullmatch(r"[A-Za-z ]+", rhs):
        return False
    has_math = bool(re.search(r"[0-9+\-*/^×÷·√()²³π\u2212\u2206\u00b1]", rhs)) or len(rw) <= 2
    if not has_math and len(rw) > 1 and not re.search(r"[×*·]", rhs):
        return False
    if re.fullmatch(r"[\d\s]+", lhs) and not re.search(r"[+\-*/×÷^]", lhs):
        return False
    return True


_INLINE = re.compile(
    r"(?<![A-Za-z0-9_])([A-Za-z\u0370-\u03ff][A-Za-z0-9_\u0370-\u03ff]*(?:\([^)=]{0,14}\))?\s*=\s*[^,;]+?)"
    r"(?=\s+(?:where|when|if|and|in which|with|for|is|are|then|so)\b|[,;]|\.\s|\.$|$)"
)


def _trim_tail(cand):
    """Drop trailing prose words that the pattern swallowed ("v = u + at holds" -> "v = u + at")."""
    tokens = cand.split(" ")
    ops = {"+", "-", "*", "/", "×", "÷", "·", "=", "^", "±", "−"}
    while len(tokens) > 3 and re.fullmatch(r"[a-z]{4,}[.,]?", tokens[-1]) and tokens[-1].strip(".,") not in FUNCS | GREEK_WORDS \
            and tokens[-2] not in ops:
        tokens.pop()
    return " ".join(tokens)


_NOT_MATH = {"a", "an", "of", "is", "to", "in", "as", "if", "so", "or", "by", "at", "on", "the", "and", "for", "it", "we", "be"}


def _extend_left(sentence, start):
    """Pull in "ax^2 + bx + " or "∫ x^n " that sit directly before the matched "lhs = ..."."""
    while True:
        prefix = sentence[:start]
        m = re.search(r"([A-Za-z0-9²³π().^_{}√]+)\s*[+\-*/×÷]\s*$", prefix)
        if m:
            start = m.start(1)
            continue
        m = re.search(r"(\S+)\s+$", prefix)
        if m and m.group(1).lower() not in _NOT_MATH and (re.search(r"[\^_∫∑∏√²³]", m.group(1)) or re.fullmatch(r"[∫∑∏]", m.group(1))):
            start = m.start(1)
            continue
        return start


def find_inline_formulas(sentence):
    """Equations embedded in a sentence ("... states that F = ma where ...")."""
    found = []
    for m in _INLINE.finditer(sentence):
        begin = _extend_left(sentence, m.start(1))
        cand = _trim_tail(sentence[begin:m.end(1)].strip().rstrip("."))
        if looks_like_equation(cand) and cand not in found:
            found.append(cand)
    return found


_VAR = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z\u0370-\u03ff](?:_?\{?[A-Za-z0-9]{1,3}\}?)?)\s*(?:=|:|–|-|—|is|denotes|represents|stands for|being)\s+"
    r"((?:the |a |an )?[A-Za-z][A-Za-z \-']{2,60}?)"
    r"(?=\s*(?:,|;|\.|\)|$)|\s+and\s+[A-Za-z\u0370-\u03ff](?:_?\{?[A-Za-z0-9]{1,3}\}?)?\s*(?:=|:|–|-|—|is)(?=\s))"
)


def parse_variables(text):
    """[('v', 'final velocity'), ...] from "where v = final velocity, u = initial velocity"."""
    text = re.sub(r"^\s*(where|here|given|symbols?|notation|let|with)\b[:,]?\s*", "", text.strip(), flags=re.I)
    out, seen = [], set()
    for m in _VAR.finditer(text):
        sym, meaning = m.group(1), re.sub(r"^(the|a|an) ", "", m.group(2).strip(), flags=re.I)
        if sym not in seen and len(meaning.split()) <= 8:
            seen.add(sym)
            out.append((sym, meaning))
    return out


# --------------------------------------------------------------- conversion
def _top_level(s, chars):
    depth, pos = 0, []
    for i, ch in enumerate(s):
        if ch in "({[":
            depth += 1
        elif ch in ")}]":
            depth -= 1
        elif depth == 0 and ch in chars:
            pos.append(i)
    return pos


def _strip_outer(s):
    s = s.strip()
    while s.startswith("(") and s.endswith(")") and len(_top_level(s[1:-1], "(")) == 0 and s.count("(") == s.count(")"):
        inner = s[1:-1]
        depth = 0
        ok = True
        for ch in inner:
            depth += (ch == "(") - (ch == ")")
            if depth < 0:
                ok = False
                break
        if not ok:
            break
        s = inner.strip()
    return s


_SCR = r"(?:[_^]\{[^{}]*\})*"
_ATOM = r"(\([^()]*\)|(?:\\[A-Za-z]+(?:\{[^{}]*\})+|[A-Za-z0-9.]+)" + _SCR + ")"


def _fractions(s):
    slashes = _top_level(s, "/")
    if len(slashes) == 1 and not _top_level(s, "+-"):
        i = slashes[0]
        if s[:i].endswith(" ") and s[i + 1:].startswith(" "):
            return r"\frac{%s}{%s}" % (_strip_outer(s[:i]), _strip_outer(s[i + 1:]))
    prev = None
    while prev != s:
        prev = s
        s = re.sub(_ATOM + r"\s*/\s*" + _ATOM, lambda m: r"\frac{%s}{%s}" % (_strip_outer(m.group(1)), _strip_outer(m.group(2))), s, count=1)
    return s


def _is_chem(s):
    if not re.search(r"->|→|⇌|<=>|=", s):
        return False
    tokens = [t for t in re.split(r"\s*(?:\+|->|→|⇌|<=>|=)\s*", s.strip()) if t]
    if len(tokens) < 2:
        return False
    pat = re.compile(r"^\d*(?:[A-Z][a-z]?\d*|\([A-Za-z0-9]+\)\d*)+(?:\^?\{?\d*[+-]\}?)?(?:\s*\((?:s|l|g|aq)\))?$")
    return all(pat.match(t) for t in tokens) and any(re.search(r"[A-Z][a-z]?\d|\)\d", t) or len(tokens) >= 2 for t in tokens) \
        and bool(re.search(r"->|→|⇌|<=>", s) or any(re.search(r"[A-Z][a-z]?\d", t) for t in tokens))


def _chem_latex(s):
    s = s.replace("<=>", "⇌").replace("->", "→")
    out = []
    for part in re.split(r"(\s*(?:\+|→|⇌|=)\s*)", s):
        p = part.strip()
        if p in ("→", "⇌", "+", "="):
            out.append({"→": r" \rightarrow ", "⇌": r" \rightleftharpoons ", "+": " + ", "=": " = "}[p])
            continue
        p = re.sub(r"\((s|l|g|aq)\)", r"_{(\1)}", p)
        p = re.sub(r"([A-Za-z\)])(\d+)", r"\1_{\2}", p)
        p = re.sub(r"\^\{?(\d*[+-])\}?", r"^{\1}", p)
        out.append(r"\mathrm{%s}" % p if p else "")
    return "".join(out).strip()


_COMMON3 = {"sum", "net", "tax", "age", "air", "sea", "pay", "gas", "oil", "top", "low", "all", "one", "two", "rate", "gdp"}


def _is_real_word(w):
    if w in GREEK_WORDS or w.lower() in FUNCS:
        return True
    if w.isupper():
        return len(w) >= 5
    if not (w.islower() or (w[0].isupper() and w[1:].islower())):
        return False  # mixed case such as nRT, PV
    lw = w.lower()
    if len(lw) == 3:
        return lw in _COMMON3
    return len(lw) >= 4 and bool(re.search(r"[aeiouy]", lw))


def _wrap_words(s):
    def repl(m):
        tok = m.group(0)
        if tok.startswith("\\"):
            return tok
        words = tok.split()
        if all(len(w) <= 2 for w in words) or not any(_is_real_word(w) for w in words):
            return tok
        if len(words) == 1 and tok in GREEK_WORDS:
            return "\\" + tok
        if len(words) == 1 and tok.lower() in FUNCS:
            return "\\" + tok.lower()
        return r"\mathrm{%s}" % r"\ ".join(words)

    return re.sub(r"\\[A-Za-z]+|(?<!\\)[A-Za-z]+(?:[ \t]+[A-Za-z]+)*(?![A-Za-z{])", repl, s)


def clean_latex_input(raw):
    s = raw.strip()
    m = re.fullmatch(r"\$\$(.+)\$\$|\$(.+)\$|\\\[(.+)\\\]|\\\((.+)\\\)", s, flags=re.S)
    if m:
        s = next(g for g in m.groups() if g)
    return s.strip()


def to_latex(raw):
    """Best-effort LaTeX for a formula written as plain text, Unicode maths or LaTeX."""
    s = clean_latex_input(raw)
    if not s:
        return ""
    if has_latex(s) and "\\" in s:
        return s
    s = s.rstrip(" .;,")
    if _is_chem(s):
        return _chem_latex(s)
    for ch, (a, b) in {"½": (1, 2), "¼": (1, 4), "¾": (3, 4), "⅓": (1, 3), "⅔": (2, 3), "⅕": (1, 5), "⅛": (1, 8)}.items():
        s = s.replace(ch, r"\frac{%d}{%d}" % (a, b))
    s = s.replace("**", "^").replace("<=", "≤").replace(">=", "≥").replace("!=", "≠").replace("+-", "±").replace("~=", "≈")
    s = s.replace("->", "→")
    s = re.sub("[" + "".join(SUP) + "]+", lambda m: "^{" + "".join(SUP[c] for c in m.group(0)) + "}", s)
    s = re.sub("[" + "".join(SUB) + "]+", lambda m: "_{" + "".join(SUB[c] for c in m.group(0)) + "}", s)
    s = s.replace("√(", "sqrt(")
    s = re.sub(r"√\s*([A-Za-z0-9.]+(?:\^\{[^}]*\})?)", r"sqrt(\1)", s)
    for _ in range(4):
        s = re.sub(r"sqrt\(([^()]*)\)", r"\\sqrt{\1}", s)
    s = re.sub(r"cbrt\(([^()]*)\)", r"\\sqrt[3]{\1}", s)
    s = re.sub(r"\^\(([^()]*)\)", r"^{\1}", s)
    s = re.sub(r"\^(-?[A-Za-z0-9.]+)", r"^{\1}", s)
    s = re.sub(r"_\(([^()]*)\)", r"_{\1}", s)
    s = re.sub(r"_([A-Za-z0-9]+)(?![A-Za-z0-9}])", r"_{\1}", s)
    s = re.sub(r"(?<![A-Za-z0-9_\\])([A-Za-z])(\d{1,2})(?![A-Za-z0-9])", r"\1_{\2}", s)
    s = re.sub(r"\bpi\b", r"\\pi", s)
    s = s.replace("*", r" \cdot ")
    for ch, name in GREEK.items():
        s = s.replace(ch, "\\" + name + " ")
    parts = re.split(r"(=|≤|≥|≠|≈|∝|→|⇌)", s)
    parts = [p if p in ("=", "≤", "≥", "≠", "≈", "∝", "→", "⇌") else _fractions(p) for p in parts]
    s = "".join(parts)
    for ch, rep in SYMBOLS.items():
        s = s.replace(ch, rep)
    s = _wrap_words(s)
    s = re.sub(r"\s*(=)\s*", r" \1 ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if s.count("{") != s.count("}"):
        return ""
    return s


# ------------------------------------------------------------------ speech
_SAY = {
    r"\times": "times", r"\cdot": "times", r"\div": "divided by", r"\pm": "plus or minus", r"\mp": "minus or plus",
    r"\le": "is less than or equal to", r"\ge": "is greater than or equal to", r"\ne": "is not equal to",
    r"\approx": "is approximately equal to", r"\propto": "is proportional to", r"\infty": "infinity",
    r"\rightarrow": "gives", r"\Rightarrow": "implies", r"\rightleftharpoons": "is in equilibrium with",
    r"\sum": "the sum of", r"\int": "the integral of", r"\prod": "the product of", r"\partial": "partial",
    r"\nabla": "nabla", r"\hbar": "h bar", r"\circ": "degrees", r"\%": "percent", r"\ldots": "and so on",
    r"\therefore": "therefore", r"\in": "belongs to", r"\ll": "is much less than", r"\gg": "is much greater than",
    r"\equiv": "is identical to",
}


def _balanced(s, i):
    """s[i] == '{': return (content, index after the matching '}')."""
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
    return s[i + 1:], len(s)


def _hold_mathrm(s, holders):
    out, i = [], 0
    while True:
        j = s.find(r"\mathrm{", i)
        if j < 0:
            out.append(s[i:])
            break
        out.append(s[i:j])
        content, end = _balanced(s, j + len(r"\mathrm"))
        content = content.replace("\\ ", " ")
        content = re.sub(r"_\{([^{}]*)\}", r" sub \1 ", content)
        if not re.search(r"[a-z]{3,}", content):
            content = re.sub(r"([A-Z][a-z]?)", r" \1 ", content)
        holders.append(re.sub(r"\s+", " ", content).strip())
        out.append(f" \x00{len(holders) - 1}\x00 ")
        i = end
    return "".join(out)


def to_speech(raw, latex=None):
    """Spoken form: "v = u + at" -> "v equals u plus a t"."""
    s = latex or to_latex(raw) or raw
    holders = []
    s = _hold_mathrm(s, holders)
    s = re.sub(r"(?<![\\A-Za-z])[A-Za-z]{2,}(?![A-Za-z])", lambda m: " ".join(m.group(0)), s)
    s = re.sub(r"\^\{?2\}?", " squared ", s)
    s = re.sub(r"\^\{?3\}?", " cubed ", s)
    s = re.sub(r"\^\{([^{}]*)\}", r" to the power \1 ", s)
    s = re.sub(r"\^([A-Za-z0-9])", r" to the power \1 ", s)
    s = re.sub(r"_\{([^{}]*)\}", r" sub \1 ", s)
    s = re.sub(r"_([A-Za-z0-9])", r" sub \1 ", s)
    for _ in range(5):
        s = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r" \1 over \2 ", s)
        s = re.sub(r"\\sqrt\[3\]\{([^{}]*)\}", r" cube root of \1 ", s)
        s = re.sub(r"\\sqrt\{([^{}]*)\}", r" square root of \1 ", s)
    for cmd, say in sorted(_SAY.items(), key=lambda kv: -len(kv[0])):
        s = s.replace(cmd, f" {say} ")
    s = re.sub(r"\\([A-Za-z]+)", lambda m: " " + m.group(1) + " ", s)
    s = s.replace("=", " equals ").replace("+", " plus ").replace("/", " divided by ")
    s = re.sub(r"(?<=[\w)])\s*-\s*(?=[\w(])", " minus ", s)
    s = re.sub(r"^\s*-\s*", "minus ", s)
    s = re.sub(r"[{}()$\\]", " ", s)
    s = re.sub(r"\x00(\d+)\x00", lambda m: holders[int(m.group(1))], s)
    return re.sub(r"\s+", " ", s).strip()


# ---------------------------------------------------------- picture output
_MPL_LOCK = threading.Lock()


def _mathtext_ok(latex):
    try:
        import matplotlib

        matplotlib.use("Agg", force=False)
        from matplotlib.mathtext import MathTextParser

        MathTextParser("path").parse(f"${latex}$")
        return True
    except Exception:
        return False


def render_png(latex, out_dir, fontsize=30, color="#12263F"):
    """Draw a formula to a transparent PNG. Returns (path, width_px, height_px) or None if it cannot be drawn."""
    if not latex:
        return None
    if re.fullmatch(r"[0-9A-Fa-f]{6}", color):
        color = "#" + color
    key = hashlib.sha1(f"{latex}|{fontsize}|{color}".encode()).hexdigest()[:20]
    path = os.path.join(out_dir, f"eq_{key}.png")
    with _MPL_LOCK:
        try:
            if os.path.exists(path):
                from PIL import Image

                with Image.open(path) as im:
                    return path, im.width, im.height
            import matplotlib

            matplotlib.use("Agg", force=False)
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            from matplotlib.figure import Figure

            if not _mathtext_ok(latex):
                return None
            os.makedirs(out_dir, exist_ok=True)
            fig = Figure(figsize=(0.1, 0.1), dpi=300)
            FigureCanvasAgg(fig)
            fig.patch.set_alpha(0)
            fig.text(0, 0, f"${latex}$", fontsize=fontsize, color=color, math_fontfamily="stix")
            fig.savefig(path, dpi=300, bbox_inches="tight", pad_inches=0.06, transparent=True)
            from PIL import Image

            with Image.open(path) as im:
                return path, im.width, im.height
        except Exception:
            return None


def formula_key(raw):
    return re.sub(r"\s+", "", raw.lower())
