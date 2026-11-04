"""Tests for the Gemini thinking-level setting and the diagnostic script (no real API calls)."""
import io
import json
import os
import runpy
import sys
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import pytest

import analysis
import app as app_module
from tests.fakes import fake_response

CV = "Python developer with Flask, AWS and Linux experience. " * 2
JOB = "We are hiring a junior cloud engineer with Python and AWS skills. " * 2
SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "gemini_diagnose.py")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.delenv("GEMINI_THINKING_LEVEL", raising=False)
    app_module.limiter.enabled = False
    with app_module.app.test_client() as c:
        yield c
    app_module.limiter.enabled = True


def sent_config(mock_post):
    return mock_post.call_args.kwargs["json"]["generationConfig"]


@patch("app.requests.post")
def test_thinking_level_is_low_by_default(mock_post, client):
    mock_post.return_value = fake_response()
    client.post("/api/analyze", json={"cv": CV, "job": JOB})
    assert sent_config(mock_post)["thinkingConfig"] == {"thinkingLevel": "low"}
    assert sent_config(mock_post)["responseMimeType"] == "application/json"


@pytest.mark.parametrize("value, expected", [("medium", {"thinkingLevel": "medium"}), ("HIGH", {"thinkingLevel": "high"}),
                                             ("nonsense", {"thinkingLevel": "low"})])
@patch("app.requests.post")
def test_thinking_level_can_be_configured(mock_post, client, monkeypatch, value, expected):
    monkeypatch.setenv("GEMINI_THINKING_LEVEL", value)
    mock_post.return_value = fake_response()
    client.post("/api/analyze", json={"cv": CV, "job": JOB})
    assert sent_config(mock_post)["thinkingConfig"] == expected


@pytest.mark.parametrize("value", ["", "default", "off"])
@patch("app.requests.post")
def test_thinking_config_can_be_left_to_the_model(mock_post, client, monkeypatch, value):
    monkeypatch.setenv("GEMINI_THINKING_LEVEL", value)
    mock_post.return_value = fake_response()
    client.post("/api/analyze", json={"cv": CV, "job": JOB})
    assert "thinkingConfig" not in sent_config(mock_post)


def test_build_request_keeps_the_schema_with_and_without_thinking():
    for level in ("low", None):
        config = analysis.build_request(CV, JOB, "sv", level)["generationConfig"]
        assert config["responseSchema"] is analysis.RESPONSE_SCHEMA


# ---------- diagnostic script ----------

def run_diagnose(responses, monkeypatch, args=()):
    monkeypatch.setenv("GEMINI_API_KEY", "SECRET-KEY-VALUE-12345")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(sys, "argv", ["gemini_diagnose.py", *args])
    out = io.StringIO()
    with patch("requests.request", side_effect=responses), redirect_stdout(out), pytest.raises(SystemExit) as exit_info:
        runpy.run_path(SCRIPT, run_name="__main__")
    return out.getvalue(), exit_info.value.code


def http(status, body):
    resp = MagicMock(ok=status < 400, status_code=status, text=json.dumps(body))
    resp.json.return_value = body
    return resp


MODELS = {"models": [{"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
                     {"name": "models/gemini-3.6-flash", "supportedGenerationMethods": ["generateContent"]}]}


def test_diagnose_reports_success_without_printing_the_key(monkeypatch):
    real = fake_response().json.return_value
    real["usageMetadata"] = {"thoughtsTokenCount": 40, "candidatesTokenCount": 300}
    output, code = run_diagnose([http(200, MODELS), http(200, real), http(200, real), http(200, real)], monkeypatch)
    assert code == 0
    assert "Gemini works with thinking level 'low'" in output
    assert "Parsed: score 68%" in output
    assert "SECRET-KEY-VALUE" not in output


def test_diagnose_detects_a_rejected_key(monkeypatch):
    body = {"error": {"message": "API key not valid. Please pass a valid API key. SECRET-KEY-VALUE-12345"}}
    output, code = run_diagnose([http(400, body)], monkeypatch)
    assert code == 1 and "Key/access  FAIL" in output
    assert "SECRET-KEY-VALUE" not in output and "<key>" in output


def test_diagnose_detects_an_unavailable_model(monkeypatch):
    output, code = run_diagnose([http(200, MODELS)], monkeypatch, ["--model", "gemini-9-ultra"])
    assert code == 1 and "NOT available" in output and "gemini-3.6-flash" in output


def test_diagnose_reports_timeouts_quickly(monkeypatch):
    import requests
    output, code = run_diagnose([http(200, MODELS), requests.Timeout(), requests.Timeout(), requests.Timeout()],
                                monkeypatch, ["--timeout", "5"])
    assert code == 1 and "TIMEOUT (no answer within 5 s)" in output and "Try another model" in output
