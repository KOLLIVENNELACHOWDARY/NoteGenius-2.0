"""Real-browser checks. The unit tests post forms by hand, so they cannot catch a button that sends nothing when clicked.
Skipped automatically when Playwright or a Chromium browser is not installed."""
import glob
import os
import threading

import pytest

from conftest import SAMPLE

sync_api = pytest.importorskip("playwright.sync_api")


def _chromium():
    for pattern in (os.environ.get("CHROMIUM_PATH", ""), "/opt/pw-browsers/chromium", "/usr/bin/chromium", "/usr/bin/chromium-browser",
                    "/usr/bin/google-chrome"):
        if pattern and os.path.exists(pattern):
            return pattern
    found = glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux/chrome"))
    return found[0] if found else None


@pytest.fixture()
def live(app):
    from werkzeug.serving import make_server

    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


def test_start_quiz_button_really_starts_the_quiz(live):
    exe = _chromium()
    if not exe:
        pytest.skip("no Chromium available")
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe)
        page = browser.new_page()
        page.goto(live + "/")
        page.fill("#input_text", SAMPLE)
        page.click("form[action*=text_input] button[type=submit]")
        page.goto(live + "/mcq")
        page.click("button[value=start_quiz]")
        page.wait_for_selector("input[name=option]", timeout=10000)
        assert "Question 1 of" in page.inner_text("main")
        page.click("label.option >> nth=0")
        page.click("button[value=submit_answer]")
        page.wait_for_selector("button[value=next_question]", timeout=10000)
        browser.close()
