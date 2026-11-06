"""Security and robustness tests for the Flask app (the Gemini API is always mocked)."""
import json
import logging
import os
import re
from unittest.mock import MagicMock, patch

import pytest
import requests

import app as app_module
from tests.fakes import FAKE_ANALYSIS, fake_response

CV = "Python developer with Flask, AWS and Linux experience. " * 2
JOB = "We are hiring a junior cloud engineer with Python and AWS skills. " * 2


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    app_module.limiter.enabled = False
    with app_module.app.test_client() as c:
        yield c
    app_module.limiter.enabled = True


def analyze(client, **body):
    return client.post("/api/analyze", json={"cv": CV, "job": JOB, **body})


# ---------- security headers ----------

def test_security_headers_on_pages(client):
    r = client.get("/")
    csp = r.headers["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "Strict-Transport-Security" not in r.headers  # only sent over HTTPS


def test_hsts_is_sent_over_https(client):
    r = client.get("/", base_url="https://careerbridge.example")
    assert r.headers["Strict-Transport-Security"].startswith("max-age=31536000")


@patch("app.requests.post")
def test_api_responses_are_never_cached(mock_post, client):
    mock_post.return_value = fake_response()
    assert analyze(client).headers["Cache-Control"] == "no-store"


def test_page_loads_no_third_party_scripts_or_styles(client):
    html = client.get("/").get_data(as_text=True)
    sources = re.findall(r'(?:src|href)="([^"]+)"', html)
    assert sources and all(s.startswith(("/", "#")) for s in sources), sources
    assert not re.search(r"(src|href)=\"(https?:)?//", html)


def test_static_files_are_served_with_caching(client):
    r = client.get("/static/js/app.js")
    assert r.status_code == 200 and "max-age=86400" in r.headers["Cache-Control"]


# ---------- input validation ----------

@pytest.mark.parametrize("payload", [[1, 2], "hello", 42, None])
def test_non_object_json_returns_400_json(client, payload):
    r = client.post("/api/analyze", data=json.dumps(payload), content_type="application/json")
    assert r.status_code == 400 and r.is_json and "error" in r.get_json()


@pytest.mark.parametrize("cv, job", [({"a": "b" * 40}, JOB), (CV, ["c" * 40]), (12345, JOB)])
def test_non_text_fields_are_rejected(client, cv, job):
    r = client.post("/api/analyze", json={"cv": cv, "job": job})
    assert r.status_code == 400
    assert "must be sent as text" in r.get_json()["error"]


def test_unknown_language_is_rejected(client):
    r = analyze(client, language="fr")
    assert r.status_code == 400 and "language" in r.get_json()["error"]


def test_oversized_request_body_returns_413(client):
    big = json.dumps({"cv": "a" * (7 * 1024 * 1024), "job": JOB})
    r = client.post("/api/analyze", data=big, content_type="application/json")
    assert r.status_code == 413 and r.is_json


@pytest.mark.parametrize("method, path, status", [("get", "/api/analyze", 405), ("get", "/api/unknown", 404)])
def test_api_errors_are_json(client, method, path, status):
    r = getattr(client, method)(path)
    assert r.status_code == status and r.is_json


# ---------- configuration ----------

@pytest.mark.parametrize("key", ["replace_with_your_key", "", "   "])
@patch("app.requests.post")
def test_placeholder_key_is_treated_as_missing(mock_post, client, monkeypatch, key):
    monkeypatch.setenv("GEMINI_API_KEY", key)
    r = analyze(client)
    assert r.status_code == 503 and "not configured" in r.get_json()["error"]
    mock_post.assert_not_called()


@patch("app.requests.post")
def test_invalid_model_name_is_not_put_in_the_url(mock_post, client, monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "../../evil?x=1")
    assert analyze(client).status_code == 503
    mock_post.assert_not_called()


def test_gemini_timeout_is_below_gunicorn_timeout():
    config = {}
    with open(os.path.join(os.path.dirname(app_module.__file__), "deploy", "gunicorn.conf.py"), encoding="utf-8") as f:
        exec(f.read(), config)  # noqa: S102 - trusted file from this repository
    assert app_module.GEMINI_CONNECT_TIMEOUT + app_module.GEMINI_READ_TIMEOUT < config["timeout"]


# ---------- AI service failures ----------

@pytest.mark.parametrize("error, status", [(requests.Timeout(), 504), (requests.ConnectionError(), 502)])
def test_network_problems_return_clear_errors(client, error, status):
    with patch("app.requests.post", side_effect=error):
        r = analyze(client)
    assert r.status_code == status and r.is_json


@pytest.mark.parametrize("upstream, status", [(429, 503), (400, 502), (500, 502)])
@patch("app.requests.post")
def test_upstream_http_errors(mock_post, client, upstream, status):
    mock_post.return_value = fake_response(status=upstream)
    assert analyze(client).status_code == status


@patch("app.requests.post")
def test_non_json_upstream_body_returns_502(mock_post, client):
    resp = MagicMock(ok=True, status_code=200)
    resp.json.side_effect = ValueError("no json")
    mock_post.return_value = resp
    assert analyze(client).status_code == 502


@patch("app.requests.post")
def test_blocked_answer_returns_422(mock_post, client):
    resp = MagicMock(ok=True, status_code=200)
    resp.json.return_value = {"promptFeedback": {"blockReason": "SAFETY"}}
    mock_post.return_value = resp
    assert analyze(client).status_code == 422


@patch("app.requests.post")
def test_malformed_ai_json_returns_502(mock_post, client):
    resp = MagicMock(ok=True, status_code=200)
    resp.json.return_value = {"candidates": [{"content": {"parts": [{"text": "{not valid json"}]}}]}
    mock_post.return_value = resp
    r = analyze(client)
    assert r.status_code == 502 and "incomplete" in r.get_json()["error"]


@patch("app.requests.post")
def test_swedish_output_is_requested(mock_post, client):
    mock_post.return_value = fake_response()
    r = analyze(client, language="sv")
    prompt = mock_post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
    assert r.get_json()["language"] == "sv" and "Write all text values in Swedish." in prompt


# ---------- privacy in logs ----------

@patch("app.requests.post")
def test_cv_text_and_key_are_never_logged(mock_post, client, caplog):
    secret_cv = "UNIQUE-CV-MARKER-123 " * 3
    caplog.set_level(logging.DEBUG)
    mock_post.return_value = fake_response(status=400)
    client.post("/api/analyze", json={"cv": secret_cv, "job": JOB})
    mock_post.return_value = fake_response()
    client.post("/api/analyze", json={"cv": secret_cv, "job": JOB})
    assert "UNIQUE-CV-MARKER" not in caplog.text
    assert "test-key-not-real" not in caplog.text
    assert "Analysis done" in caplog.text


def test_unexpected_errors_do_not_leak_details(client):
    with patch("app.analysis.build_request", side_effect=RuntimeError("secret internal detail")):
        r = analyze(client)
    assert r.status_code == 500 and r.is_json
    assert "secret internal detail" not in r.get_data(as_text=True)


# ---------- rate limiting ----------

@patch("app.requests.post")
def test_analyze_is_rate_limited(mock_post, client):
    mock_post.return_value = fake_response()
    app_module.limiter.enabled = True
    app_module.limiter.reset()
    try:
        codes = [analyze(client).status_code for _ in range(6)]
    finally:
        app_module.limiter.reset()
    assert codes[:5] == [200] * 5
    assert codes[5] == 429
    assert mock_post.call_count == 5


def test_health_is_not_rate_limited(client):
    app_module.limiter.enabled = True
    app_module.limiter.reset()
    try:
        assert all(client.get("/health").status_code == 200 for _ in range(30))
    finally:
        app_module.limiter.reset()


@patch("app.requests.post")
def test_result_matches_the_fake_answer(mock_post, client):
    mock_post.return_value = fake_response()
    data = analyze(client).get_json()["analysis"]
    assert data["missing_skills"] == FAKE_ANALYSIS["missing_skills"]
