"""Fixtures for the browser (end-to-end) tests.

The Flask app runs in a background thread on a free local port. The Gemini API
is replaced by the fake answer in tests/fakes.py, so no key or internet is needed.

Run:  python -m pytest tests/e2e -v
(needs: pip install -r requirements-dev.txt  and  python -m playwright install chromium)
"""
import os
import socket
import threading
from unittest.mock import patch

import pytest

sync_api = pytest.importorskip("playwright.sync_api", reason="Playwright is not installed")

import app as app_module  # noqa: E402
from tests.fakes import fake_response  # noqa: E402
from werkzeug.serving import make_server  # noqa: E402


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    os.environ["GEMINI_API_KEY"] = "fake-key-for-browser-tests"
    app_module.limiter.enabled = False
    port = _free_port()
    server = make_server("127.0.0.1", port, app_module.app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    with patch("app.requests.post", side_effect=lambda *a, **k: fake_response()):
        thread.start()
        yield f"http://127.0.0.1:{port}"
        server.shutdown()
    app_module.limiter.enabled = True


@pytest.fixture(scope="session")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as exc:  # browser binaries missing
            pytest.skip(f"Chromium is not available: {exc}")
        yield b
        b.close()


@pytest.fixture
def page(browser, base_url):
    context = browser.new_context(viewport={"width": 1280, "height": 900}, accept_downloads=True)
    pg = context.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and pg.errors.append(m.text))
    pg.goto(base_url + "/")
    yield pg
    context.close()


@pytest.fixture
def mobile_page(browser, base_url):
    context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                  device_scale_factor=2)
    pg = context.new_page()
    pg.goto(base_url + "/")
    yield pg
    context.close()
