# Testing

CareerBridge AI has **137 automated tests**. None of them call the real Gemini API: every AI answer is a recorded-style fake (`tests/fakes.py`), so the tests are free, fast, offline and need no API key.

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m playwright install chromium     # once, for the browser tests

python -m pytest                    # everything
python -m pytest -m "not e2e"       # unit, security and upload tests only (about 2 s)
python -m pytest -m e2e             # browser and accessibility tests (about 30 s)
```

## Test suites

| File | Tests | What it covers |
|---|---|---|
| `tests/test_app.py` | 15 | The original v1 test suite: pages, health check, input validation, API key handling, model selection, prompt safety, error handling. Three tests were updated for the structured JSON answer; the rest are unchanged |
| `tests/test_analysis.py` | 30 | Prompt and JSON schema, Swedish/English output, prompt-injection hardening, validation of AI answers (score clamping, invalid JSON, lists, length limits), score labels, blocked answers |
| `tests/test_security.py` | 35 | Security headers and HSTS, no-store caching, no third-party resources, type checks, 413/404/405 as JSON, placeholder keys, model-name injection, Gemini timeouts and errors, Swedish output, **no CV text or key in logs**, no leaked internals on crashes, rate limiting, Gunicorn timeout check |
| `tests/test_upload.py` | 21 | Real PDF and DOCX files (tables, truncation), uploads kept out of temp files, missing file, wrong extensions, renamed executables, damaged and encrypted PDFs, page limit, scanned PDFs, 5 MB limit, **zip bomb**, **XXE payload** |
| `tests/e2e/test_ui.py` | 18 | Playwright + Chromium: page loads without console errors, browser validation, counters, full comparison, AI text inserted as text (XSS), Swedish option, PDF and DOCX upload, unsupported file, Nginx error pages, rate-limit message, cancel, copy, download, theme memory, clear, skip link, mobile layout |
| `tests/e2e/test_dashboard.py` | 11 | v2.1 interface: uploaded-file card, removing a file, rejected upload, progress view while waiting and after errors, dashboard counters, suggestion checklist, reduced motion, navigation links, tablet and phone layouts |
| `tests/e2e/test_accessibility.py` | 7 | axe-core WCAG 2.1 A/AA rules on the start page, results page, error state, progress view and uploaded-file card, in dark and light themes |

## Continuous integration

`.github/workflows/tests.yml` runs on every push and pull request to `main`:

- **unit** job: `pytest -m "not e2e"` on Python 3.10 and 3.12
- **browser** job: installs Chromium and runs `pytest -m e2e`

## Checks that are not automated tests

| Check | How | Result |
|---|---|---|
| Full stack (Nginx → Gunicorn → Flask) with HTTP→HTTPS redirect, TLS, headers, uploads, a 40-second AI answer and rate limiting | Local replica with a test certificate (see `docs/DEPLOYMENT.md`) | Passed |
| `nginx -t`, `systemd-analyze verify`, `shellcheck` on the deployment files | Local | Passed |
| Real Gemini answer with a real key | `python scripts/gemini_smoke_test.py` (English and Swedish) | **Not yet done** – needs the owner's API key |
| Live EC2 server, security group, real Let's Encrypt certificate | `deploy/server_audit.sh`, `deploy/verify_deployment.sh` | **Not yet done** – needs AWS access and a domain |

## Regression tests for the bugs fixed in v2

| Bug in v1 | Test |
|---|---|
| JSON array/string body → 500 HTML page | `test_non_object_json_returns_400_json` |
| CV sent as object/list was accepted | `test_non_text_fields_are_rejected` |
| No request size limit | `test_oversized_request_body_returns_413` |
| No security headers | `test_security_headers_on_pages` |
| No rate limit | `test_analyze_is_rate_limited` |
| Placeholder key from `.env.example` was sent to Gemini | `test_placeholder_key_is_treated_as_missing` |
| HTML error pages from Nginx shown as "Connection error" | `test_proxy_error_page_gives_a_helpful_message` |
| Empty form was sent to the server | `test_empty_form_is_validated_in_the_browser` |
| Gunicorn 30 s timeout shorter than the 120 s Gemini wait | `test_gemini_timeout_is_below_gunicorn_timeout` |
| 404/405 returned HTML from the API | `test_api_errors_are_json` |
