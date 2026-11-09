# Changelog

## 2.2.0 – 2026-11-09 (final polish)

### Fixed
- When printing or saving as PDF, the skill, suggestion and cover-letter cards could be invisible because their entrance animation had not finished. Print styles now always show every card.
- With "reduce motion" switched on, animation delays still applied; they are now removed as well.

### Changed
- Cover letter card: placeholders such as `[Company name]` are highlighted (built with text nodes, never HTML) and a "Before you send it" checklist uses the empty space next to the letter; stacked on phones.
- 3 new browser tests (169 in total). Screenshots updated.

## 2.1.3 – 2026-11

### Changed
- Default model is now `gemini-3.6-flash`, with `gemini-3.8-flash` as fallback. Verified with a real API call (3.6 s, valid structured answer); `gemini-3.8-flash` was overloaded ("high demand") and `gemini-2.5-flash` is no longer available to new API users.

## 2.1.2 – 2026-11

### Fixed
- Gemini 2.x models (for example `gemini-2.5-flash`) use `thinkingBudget` instead of `thinkingLevel`. The request now uses the right format for each model family, also for the fallback model. 8 new tests (165 in total).

## 2.1.1 – 2026-11

### Fixed
- Real Gemini requests timed out after 90 s. Gemini 3 Flash models "think" at level medium by default, which made the structured answer too slow. The app now sends `thinkingConfig.thinkingLevel = low` (setting `GEMINI_THINKING_LEVEL`; empty = model default).

### Added
- `scripts/gemini_diagnose.py`: fast checks with short timeouts (key and access, model availability, tiny answer, real request with low thinking).
- `scripts/gemini_smoke_test.py` now stops after 60 s instead of 90 s and shows the thinking level.
- Clear message when Google reports the model as overloaded ("high demand", HTTP 503).
- Optional `GEMINI_FALLBACK_MODEL`: tried once if the main model is overloaded (503) or rate-limited (429); not used for other errors or timeouts. The answer includes which model was used.
- 20 tests for the thinking setting, the fallback model and the diagnostic script (157 in total).

## 2.1.0 – 2026-11 (branch `feature/v2-ui-polish`)

Interface polish for the portfolio submission. No backend or API changes.

### Changed
- New home page: clear headline, three-step "how it works" strip, example result preview, navigation and a privacy section.
- CV upload area: drag-and-drop zone with an upload progress bar; after upload the file is shown as a card (type, size, pages, characters) with **Replace** and **Remove**.
- Progress view while the AI works: elapsed time, progress steps and a loading skeleton, hidden again on success, error or cancel.
- Results dashboard: score card with animated arch and count-up (off with reduced motion), "At a glance" counters, skill cards with icons, suggestions as a checklist, cover letter card with word count; download and edit actions at the top.
- Tablet layout, refined spacing, icons (inline SVG, no icon library), focus states and print styles.

### Added
- 13 browser tests (137 in total): upload card, progress view, dashboard counters, checklist, reduced motion, navigation, tablet and phone layouts, accessibility of the new states.
- `scripts/gemini_smoke_test.py` to check the real Gemini integration once with your own key.
- `docs/DEMO.md` with a short demo script.

## 2.0.0 – 2026-11 (branch `feature/v2-improvements`)

Improvement of the original internship application, keeping the same Flask architecture.

### Fixed
- Gunicorn's default 30 s worker timeout was shorter than the 120 s wait for Gemini, so slow answers failed with 502 behind Nginx. Gunicorn now uses 120 s and the Gemini wait is 10 + 90 s.
- A JSON array or string body crashed the API with a 500 HTML page.
- A CV or job ad sent as an object or list was accepted and sent to the AI.
- Requests had no size limit (a 20 MB body was read into memory).
- The placeholder key from `.env.example` was sent to Gemini and produced a misleading 502.
- Nginx error pages and CDN failures were shown as "Connection error", even after a successful analysis.
- Empty forms were sent to the server; no character counter or loading state.
- Invalid CSS (`font: 15px/1.5 inherit`) made text areas use a monospace font.
- 404 and 405 errors from the API were HTML instead of JSON.

### Security
- Content-Security-Policy, X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy, COOP; HSTS over HTTPS.
- Rate limiting per IP (Flask-Limiter) and in Nginx.
- `Cache-Control: no-store` on API responses; CV text and keys never logged.
- Prompt-injection hardening: data tags in user text are neutralised.
- AI answers validated against a schema; output inserted with `textContent` only.
- Third-party scripts removed (marked and DOMPurify from a CDN are no longer needed).
- Model name validated before it is used in the URL.

### Added
- Structured Gemini output (JSON schema): match score shown as an **AI estimate**, matching and missing skills, CV suggestions, cover letter draft.
- PDF and DOCX upload with in-memory processing, type and signature checks, page and size limits, zip-bomb and XXE protection.
- Output language: English or Swedish (interface stays in English).
- New interface: dark and light themes, responsive layout, upload with drag and drop, example data, cancel, copy letter, download report, accessible error messages.
- Self-hosted fonts (Bricolage Grotesque, Atkinson Hyperlegible, SIL OFL).
- Tests: 109 new (124 in total), including Playwright browser tests and axe-core accessibility checks; CI runs both.
- Deployment files: Gunicorn config, hardened systemd service, Nginx with HTTP→HTTPS redirect and TLS, Let's Encrypt bootstrap, renewal timer and hook, read-only server and site check scripts.
- Documentation: architecture, security, testing and deployment guides.

## 1.0.0 – 2026-10

First version, built during the Nation Enterprises internship and run on AWS EC2: Flask app with a Gemini-based CV and job ad analysis in Markdown.
