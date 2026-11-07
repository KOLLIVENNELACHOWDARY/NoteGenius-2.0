"""Server-side per-visitor storage.

Flask's default session lives in a 4 KB cookie, which silently breaks as soon as a
PDF's text is stored in it. Here the cookie only holds a random id; the notes and
quiz state live in small JSON files under DATA_DIR/sessions.
"""
import json
import os
import re
import time
import uuid

from flask import current_app, session

_SID_RE = re.compile(r"^[0-9a-f]{32}$")


def _dir():
    path = os.path.join(current_app.config["DATA_DIR"], "sessions")
    os.makedirs(path, exist_ok=True)
    return path


def _path(sid):
    return os.path.join(_dir(), f"{sid}.json")


def _sid(create=False):
    sid = session.get("sid")
    if sid and _SID_RE.match(sid):
        return sid
    if create:
        sid = uuid.uuid4().hex
        session["sid"] = sid
        session.permanent = True
        return sid
    return None


def load():
    sid = _sid()
    if not sid:
        return {}
    try:
        with open(_path(sid), encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save(state):
    sid = _sid(create=True)
    final = _path(sid)
    tmp = f"{final}.{uuid.uuid4().hex}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh)
    os.replace(tmp, final)


def get(key, default=None):
    return load().get(key, default)


def update(**values):
    state = load()
    state.update(values)
    save(state)
    return state


def drop(*keys):
    state = load()
    changed = False
    for key in keys:
        if key in state:
            del state[key]
            changed = True
    if changed:
        save(state)


def purge_dir(directory, max_age_seconds):
    """Delete files in a directory that are older than max_age_seconds."""
    cutoff = time.time() - max_age_seconds
    try:
        names = os.listdir(directory)
    except FileNotFoundError:
        return
    for name in names:
        full = os.path.join(directory, name)
        try:
            if os.path.isfile(full) and os.path.getmtime(full) < cutoff:
                os.remove(full)
        except OSError:
            pass
