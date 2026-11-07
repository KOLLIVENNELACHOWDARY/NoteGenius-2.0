"""Tell programs from prose and formulas.

Notes often contain source code (C, Java, Python, SQL, HTML ...). Code must stay a code block:
it is never a formula, a definition or a key point.

line_score(line) -> 0 not code, 1 ambiguous (e.g. "x = 5"), 2 clearly code.
find_run(lines, i)  -> (end_index, text) when a block of code starts at lines[i], else None.
"""
import re

_STRONG = [
    r"^\s*#\s*(include|define|ifdef|ifndef|endif|pragma)\b",
    r"^\s*(import|from)\s+[\w.]+(\s+import\b.*|\s+as\s+\w+)?\s*;?\s*$",
    r"^\s*(def|class)\s+\w+.*:\s*$",
    r"^\s*(public|private|protected|static|final|abstract)\b.*[({;]\s*$",
    r"^\s*(int|float|double|char|long|short|void|bool|boolean|string|String|var|let|const|auto|unsigned)\b[\s*&]+\w+\s*(\(|=|;|\[|,)",
    r"^\s*(if|for|while|switch|elif|else\s+if)\b\s*\(.*\)\s*\{?\s*$",
    r"^\s*(if|elif|while|for)\b.*:\s*$",
    r"^\s*(else|try|finally|do)\s*[:{]?\s*$",
    r"^\s*(except|catch)\b.*[:{)]\s*$",
    r"^\s*return\b.*;\s*$",
    r"^\s*return\s*;?\s*$",
    r"^\s*(print|printf|scanf|println|puts|input)\s*\(",
    r"\b(System\.out\.\w+|console\.log|cout\s*<<|cin\s*>>|std::)",
    r"^\s*(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+(TABLE|DATABASE|INDEX|VIEW)|DROP\s+TABLE|ALTER\s+TABLE)\b.*",
    r"^\s*(FROM|WHERE|GROUP\s+BY|ORDER\s+BY|HAVING|VALUES|JOIN)\b.*[;)]?\s*$",
    r"^\s*</?[a-zA-Z][\w-]*(\s[^<>]*)?/?>",
    r"^\s*(sudo\s+|pip\s+install|npm\s+(install|run)|git\s+(clone|commit|push|add)|cd\s+\S+|ls\b|python3?\s+\S+\.py)",
    r"[;{}]\s*$",
    r"^\s*\w[\w.\[\]]*\s*(\+=|-=|\*=|/=|%=|\+\+|--)\s*",
    r"\w\s*(==|!=|&&|\|\|)\s*\w",
    r"^\s*(//|/\*|\*/|\*\s|--\s)",
    r"^\s*(public\s+static\s+void\s+main|int\s+main)\b",
    r"^\s*\w+\s*=\s*(new\s+\w+|\[\s*\]|\{\s*\}|input\(|int\(|float\(|str\(|list\(|dict\(|set\(|range\()",
    r"\b(self|this)\.\w+",
    r"^\s*(lambda|yield|async|await|elif|pass|break|continue)\b",
    r"^\s*\}\s*(else\b.*)?$",
    r"->\s*\w+\s*:\s*$",
]
_STRONG = [re.compile(p, re.I if "SELECT" in p or "FROM" in p else 0) for p in _STRONG]

_MATH_FUNCS = {"sin", "cos", "tan", "cot", "sec", "csc", "log", "ln", "exp", "sqrt", "max", "min", "lim", "det", "abs", "arcsin",
               "arccos", "arctan", "sinh", "cosh", "tanh", "f", "g", "h", "p", "q", "pr"}
_ASSIGN_CALL = re.compile(r"^\s*([A-Za-z_]\w*(?:\[[^\]]*\])?)\s*=\s*([A-Za-z_][\w.]*)\s*\(.*\)\s*$")
_ASSIGN = re.compile(r"^\s*([A-Za-z_]\w*(?:\[[^\]]*\])?)\s*=\s*[^=].*$")
_COMMENT_ONLY = re.compile(r"^\s*(#|//|/\*|\*)")
_PROSE_WORDS = re.compile(r"\b(the|is|are|of|that|which|this|and|to|in|for|with|can|will|be|by|as|an)\b", re.I)


def _looks_like_sentence(line):
    t = line.strip()
    words = t.split()
    if len(words) < 6:
        return False
    stops = len(_PROSE_WORDS.findall(t))
    return stops >= 3 and not re.search(r"[;{}]\s*$", t)


def line_score(line):
    t = line.strip()
    if not t:
        return 0
    if t.startswith("$") or "\\frac" in t or "\\sqrt" in t:
        return 0
    if _looks_like_sentence(t):
        return 0
    for rx in _STRONG:
        if rx.search(line):
            if rx.pattern == r"[;{}]\s*$":
                if re.match(r"^[A-Za-z_]\w*(\[[^\]]*\])?\s*=\s*[^=(]*;$", t):
                    return 1.5  # "v = u + at;" is a formula unless code lines surround it
                if re.search(r"[\^_]\{|\\[A-Za-z]", t) or not (t.endswith((";", "{")) or t == "}" or t.startswith("}")):
                    continue
            if rx.pattern.startswith("^\\s*(//") and len(t.split()) > 6:
                continue
            return 2
    m = _ASSIGN_CALL.match(t)
    if m and m.group(2).lower() not in _MATH_FUNCS and len(m.group(2)) > 1:
        return 1
    if _ASSIGN.match(t) and re.search(r"\w\s*=\s*\S", t):
        rhs = t.split("=", 1)[1].strip()
        if re.search(r"""["']""", rhs) or re.search(r"\w\[\w*\]", t) or "_" in t.split("=")[0]:
            return 1
        return 0.5
    return 0


def _is_blankish(line):
    return not line.strip()


def find_run(lines, i):
    """If a program starts at lines[i], return (end_exclusive, text)."""
    first = line_score(lines[i])
    if first < 2:
        return None
    n = len(lines)
    j, last = i, i
    strong = weak = total = 0
    blanks = 0
    while j < n:
        ln = lines[j]
        if _is_blankish(ln):
            blanks += 1
            if blanks > 1:
                break
            j += 1
            continue
        sc = line_score(ln)
        indented = ln[:1] in (" ", "\t") and ln.strip() and j > i
        if sc >= 2:
            strong += 1
        elif sc >= 0.5 or _COMMENT_ONLY.match(ln) or ln.strip() in ("{", "}", ")", "]"):
            weak += 1
        elif indented and (blanks == 0 or True) and not _looks_like_sentence(ln) and total >= 1:
            weak += 1
        else:
            break
        total += 1
        last = j
        blanks = 0
        j += 1
    if not (strong >= 2 or (strong >= 1 and total >= 3) or (strong >= 1 and first >= 2 and re.search(r"[;{}]\s*$|^\s*#include|^\s*(SELECT|INSERT|CREATE)\b", lines[i], re.I))):
        return None
    text = "\n".join(lines[i:last + 1]).rstrip()
    return last + 1, text


def is_code_line(line):
    return line_score(line) >= 2


def guess_lang(text):
    t = text
    if re.search(r"#include\s*<", t):
        return "cpp" if re.search(r"\bcout\b|std::|\bclass\b", t) else "c"
    if re.search(r"System\.out|public\s+static\s+void\s+main|\bpublic\s+class\b", t):
        return "java"
    if re.search(r"\b(SELECT|INSERT\s+INTO|CREATE\s+TABLE|UPDATE\s+\w+\s+SET|DELETE\s+FROM)\b", t, re.I):
        return "sql"
    if re.search(r"</?(html|div|body|span|p|a|ul|li|table|script|head)\b", t, re.I):
        return "html"
    if re.search(r"console\.log|=>\s*[{(]|\b(const|let)\s+\w+\s*=|function\s+\w*\(", t):
        return "javascript"
    if re.search(r"^\s*(def|class)\s+\w+|^\s*(import|from)\s+\w+|\bprint\(|^\s*(elif|except)\b|:\s*$", t, re.M):
        return "python"
    if re.search(r"\b(int|float|double|char|void)\s+\w+", t):
        return "c"
    return "code"
