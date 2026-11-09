# Security and privacy

CareerBridge AI handles CV text, which is personal data. The design goal is simple: **use the text once, never store it, never expose it over plain HTTP, and never trust anything that comes from the browser or the AI.**

## Threats and controls

| Risk | Control | Where | Tested by |
|---|---|---|---|
| API key leaks | Key only in a server-side env file (`chmod 640`), sent to Gemini in the `x-goog-api-key` header, never in URLs, logs or responses. Placeholder keys are treated as "not configured" | `app.py`, `.env.example`, `deploy/careerbridge.service` | `test_successful_analysis_uses_default_model_and_header_key`, `test_placeholder_key_is_treated_as_missing`, `test_cv_text_and_key_are_never_logged` |
| CV data over unencrypted HTTP | Port 80 only redirects to HTTPS and serves the Let's Encrypt challenge. HSTS tells browsers to use HTTPS only | `deploy/nginx/careerbridge.conf` | Local Nginx replica (see DEPLOYMENT.md), `verify_deployment.sh` |
| CV data stored on disk | Uploads are parsed in memory (custom Flask request class); Nginx keeps request bodies in memory (`client_body_buffer_size 6m`); nothing is saved to a database; API responses are `Cache-Control: no-store` | `app.py`, `cv_extract.py`, Nginx config | `test_uploads_are_not_written_to_temporary_files`, `test_api_responses_are_never_cached` |
| CV data in logs | Only status, file type, sizes, model, score and duration are logged – never text | `app.py`, `deploy/gunicorn.conf.py` | `test_cv_text_and_key_are_never_logged` |
| Cross-site scripting through AI output | AI text is inserted with `textContent` only; strict Content-Security-Policy without `unsafe-inline`; no third-party scripts | `static/js/app.js`, `app.py` | `test_ai_text_is_inserted_as_text_not_html`, `test_security_headers_on_pages`, `test_page_loads_no_third_party_scripts_or_styles` |
| Clickjacking, MIME sniffing, referrer leaks | `frame-ancestors 'none'`, `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer` | `app.py` | `test_security_headers_on_pages` |
| Prompt injection from CV or job ad | Text is wrapped in `<cv>`/`<job>` data blocks; tags inside the text are neutralised; the model is told to ignore instructions in the data; the answer must match a JSON schema and is validated | `analysis.py` | `test_user_text_cannot_close_the_data_blocks`, `test_unusable_answers_are_rejected` |
| Malformed or malicious AI answers | Score clamped to 0–100, lists deduplicated and capped, text length limited, non-JSON rejected | `analysis.py` | `tests/test_analysis.py` |
| Malicious uploads | Extension **and** file signature checked; PDF page limit, encrypted PDFs rejected; DOCX zip-bomb limits; XML entities are not resolved (XXE) | `cv_extract.py` | `tests/test_upload.py` (renamed `.exe`, zip bomb, XXE payload, damaged files) |
| Large requests (denial of service) | 6 MB request limit in Flask and Nginx, 5 MB per file, 12,000 characters per field | `app.py`, Nginx | `test_oversized_request_body_returns_413`, `test_file_over_5_mb_is_rejected` |
| API key abuse / cost | Rate limits per IP in the app (5/min, 50/day for analysis) and in Nginx; real client IP taken from Nginx only (`ProxyFix`, one trusted proxy) | `app.py`, Nginx | `test_analyze_is_rate_limited`, local Nginx replica |
| Broken input crashing the server | Type checks for every field; JSON errors for every API failure; no stack traces to users | `app.py` | `test_non_object_json_returns_400_json`, `test_unexpected_errors_do_not_leak_details` |
| Model name injection into the URL | `GEMINI_MODEL` must match `^[A-Za-z0-9._-]+$` | `app.py` | `test_invalid_model_name_is_not_put_in_the_url` |
| Compromised app process | Runs as an unprivileged `careerbridge` user under systemd with `ProtectSystem=strict`, `NoNewPrivileges`, no capabilities, private `/tmp`, memory limit | `deploy/careerbridge.service` | `systemd-analyze verify` |
| Weak TLS | TLS 1.2 and 1.3 only, session tickets off, unknown host names rejected | Nginx config | Local replica: TLS 1.1 refused, TLS 1.3 works |

## Privacy notes for users

- The CV and job ad are sent to the **Google Gemini API** to create the comparison. Google's terms for the API key's account apply.
- The app shows this in the footer and advises not to include details such as a personal identity number (personnummer).
- A public deployment should add a short privacy notice (who runs the service, what is sent to Google, that nothing is stored).

## Known limitations

- The in-memory rate limit is per Gunicorn worker. For several servers, set `RATELIMIT_STORAGE_URI` to a shared store such as Redis.
- Live Gemini behaviour (the real JSON answers) has only been tested with recorded/fake responses in this repository. Run one real analysis with your own key before a demo.
- Scanned PDFs (images without text) are not read; the user is asked to paste the text instead.

## Reporting a problem

Please open a GitHub issue without including personal data or keys.
