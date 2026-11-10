# Handover report – CareerBridge AI

**Author:** Saiedeh Babaki · Internship at Nation Enterprises · Last updated 2026-11-10

CareerBridge AI compares a CV with a job advertisement using the Google Gemini API. It was the first web application I built and hosted on AWS EC2 during the internship. Version 2 makes it secure, reliable, tested and ready for HTTPS.

## Status at a glance

| Area | Status | Evidence |
|---|---|---|
| Version 2 code | Finished, merged to `main` | PR #4, CI green on every commit |
| Automated tests | **174 passing** (135 unit/security/upload + 39 browser/accessibility) | GitHub Actions, Python 3.10 and 3.12 |
| Real Gemini answers | Verified in **English and Swedish** | Browser tests on Windows, 2026-11-09 (`gemini-3.5-flash`, about 5 s, HTTP 200) |
| Dependency security | No known vulnerabilities | `pip-audit`, 2026-11-10 |
| Static code scan | No issues | `bandit`, 2026-11-10 |
| Secrets | No API key in code or Git history | Manual and pattern search; `.env` is git-ignored |
| Deployment configuration | Ready and tested on a local replica server | `deploy/`, [DEPLOYMENT.md](DEPLOYMENT.md) |
| Live AWS deployment of version 2 | **Not done yet** – waits for approval of each step | Version 1 ran on EC2 (CloudCare-Web) |
| HTTPS | Prepared (Nginx + Let's Encrypt + free DuckDNS name) | Not yet live |

## What was done in version 2

| Before (version 1) | After (version 2) |
|---|---|
| Gunicorn stopped requests after 30 s → error 502 | Timeouts aligned (browser 115 s, Nginx 125 s, Gunicorn 120 s, Gemini 90 s) |
| Bad input could crash the API | All input validated, clear JSON errors |
| No security headers or rate limiting | CSP, HSTS, X-Frame-Options, rate limits, CV text never logged |
| Free-text AI answer | Structured JSON answer, validated before display |
| Pasted text only | PDF and DOCX upload in memory (zip-bomb and XXE protection) |
| English only | English or Swedish results |
| One fixed AI model | Fallback models when Google reports high demand; one retry on dropped connections |
| Simple page | Responsive dashboard, dark/light theme, accessible (axe-core) |
| 15 tests | 174 tests and CI |

## The hardest problem: Gemini did not answer

1. The first real test failed with error 504 after 90 seconds.
2. A diagnostic script (`scripts/gemini_diagnose.py`) checked one thing at a time: the key worked and the model existed, but Google answered "high demand" (HTTP 503).
3. `gemini-2.5-flash` was closed to new users; other models were overloaded at different times.
4. Fix: thinking level "low" for fast answers, and a list of fallback models tried in order. `gemini-3.5-flash` answered in about 5 seconds in the final tests.

## What still needs approval

Each step changes the AWS account or the server, so each is done only after explicit approval:

1. Read-only check of CloudCare-Web (console and `deploy/server_audit.sh`).
2. EBS snapshot of CloudCare-Web as a backup (about $0.40/month).
3. Elastic IP (free while attached) and a DuckDNS name (free).
4. Security group: 80/443 open, 22 limited to one IP.
5. Install version 2 (Python 3.11, Gunicorn service, Nginx, Let's Encrypt).
6. Live tests in English and Swedish, upload, cover letter and report download.

The instance **Neda-Level2** is not part of this project and is not touched.

## How to run and check it

- Local: `start-windows.bat` (Windows) or `python app.py`, then http://127.0.0.1:5055 – see [README](../README.md).
- Tests: `python -m pytest` – see [TESTING.md](TESTING.md).
- Deployment, backup and rollback: [DEPLOYMENT.md](DEPLOYMENT.md).
- Security design: [SECURITY.md](SECURITY.md). Architecture: [ARCHITECTURE.md](ARCHITECTURE.md). Demo script: [DEMO.md](DEMO.md).
