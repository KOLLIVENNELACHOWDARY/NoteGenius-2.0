"""Study plan: spread the sections over the days available, then revise and self-test."""
import datetime as dt
import math

from .structure import Document, parse


def _section_minutes(doc, sec):
    own = len(sec.text().split())
    defs = len(doc.defs_in(sec))
    fs = len(doc.formulas_in(sec))
    ts = len(doc.tables_in(sec))
    return max(5, round(own / 120 + defs * 1.5 + fs * 3 + ts * 3))


def build_plan(text, days=7, minutes_per_day=60, start=None):
    """Return {'days': [...], 'warning': str|None, 'total_minutes': int}. Each day: {n, date, focus, tasks, minutes}."""
    doc = parse(text)
    days = max(1, min(60, int(days)))
    budget = max(15, int(minutes_per_day))
    start = start or dt.date.today()
    secs = [(s, _section_minutes(doc, s)) for s in doc.all_sections() if s.title and (s.blocks)]
    if not secs:
        secs = [(next(doc.all_sections()), 10)]
    total = sum(m for _, m in secs)

    if days == 1:
        learn_days, rev_days = 1, 0
    elif days <= 3:
        learn_days, rev_days = days - 1, 1
    else:
        rev_days = max(1, round(days * 0.3))
        learn_days = days - rev_days
    per_day = total / learn_days
    plan = [{"n": i + 1, "date": start + dt.timedelta(days=i), "focus": "", "tasks": [], "minutes": 0} for i in range(days)]

    day, acc = 0, 0.0
    for sec, mins in secs:
        if acc >= per_day * 0.98 and day < learn_days - 1:
            day, acc = day + 1, 0.0
        d = plan[day]
        d["tasks"].append(f"Study “{sec.title}” (about {mins} min): read it, then write the key terms and formulas in your own words")
        d["minutes"] += mins
        acc += mins
    for d in plan[:learn_days]:
        if d["tasks"]:
            d["tasks"].append("Make flashcards for what you studied and answer them once")
            d["minutes"] += 10
            d["focus"] = "Learn"
    revision_tasks = [
        ["Go through the Flashcards deck and mark what you miss", "Review the Formula sheet: cover the right side and rewrite each formula"],
        ["Take a Multiple-choice quiz and use “Retry missed questions”", "Re-read notes only for the questions you got wrong"],
        ["Answer the Practice questions in writing, then compare with the model answers", "Read the Cheat sheet once, slowly"],
    ]
    for i, d in enumerate(plan[learn_days:]):
        d["focus"] = "Revise"
        d["tasks"] = list(revision_tasks[i % len(revision_tasks)])
        d["minutes"] = min(budget, 45)
    if days >= 2:
        last = plan[-1]
        last["focus"] = "Final check"
        last["tasks"] = ["Take a full Multiple-choice quiz (10+ questions)", "Skim the Cheat sheet and Formula sheet", "Sleep well. Do not start new topics today"]
        last["minutes"] = min(budget, 40)
    if days == 1:
        plan[0]["tasks"].append("Take a Multiple-choice quiz at the end")
        plan[0]["minutes"] += 15
        plan[0]["focus"] = "Crash course"

    busiest = max(d["minutes"] for d in plan)
    warning = None
    if busiest > budget * 1.1:
        need = math.ceil(total / learn_days / 5) * 5 + 10
        warning = f"This plan needs up to {busiest} minutes on some days, more than the {budget} you chose. Add days or raise the daily time to about {need} minutes."
    return {"days": plan, "warning": warning, "total_minutes": total + 10 * learn_days, "sections": len(secs)}
