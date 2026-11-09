# Demo guide (about 5 minutes)

A short script for showing CareerBridge AI in a meeting or interview.

## Before the demo

```bash
git checkout feature/v2-ui-polish        # or main, once the pull request is merged
pip install -r requirements.txt
python scripts/gemini_smoke_test.py      # optional: proves the real Gemini connection works (needs GEMINI_API_KEY in .env)
python app.py                            # open http://127.0.0.1:5055
```

Without an API key the whole interface still works, and the app clearly says that the AI key is not configured. For a demo without a key, show the automated tests and the screenshots in `docs/screenshots/` instead.

## 1. The problem (30 s)

"Job seekers often don't know which requirements in a job ad their CV actually proves. CareerBridge AI compares the two texts and gives an honest overview."

## 2. Upload a CV (1 min)

1. Drag a PDF or DOCX onto **Drop your CV here** (or click **choose a file**).
2. Point out the file card (type, size, pages) and that the text appears in the field so you can check it before anything is sent.
3. Mention: the file is read in memory and never stored; only PDF and DOCX up to 5 MB are accepted, and the real file content is checked, not just the file name.

Tip: **Try an example** fills in a fictional CV and job ad.

## 3. Compare (1 min)

1. Choose **Results in: Svenska** to show Swedish output, or keep English.
2. Click **Compare CV and job**. Show the progress view and the **Cancel** button.

## 4. The results dashboard (1.5 min)

- The **score** is labelled *AI estimate* – it is not a hiring prediction.
- **At a glance**: skills found, gaps to close, number of suggestions.
- **Found in your CV** (green) and **Asked for, but not shown** (amber).
- **Suggestions** can be ticked off as you update the CV.
- **Cover letter draft**: copy it, or **Download report (.txt)**.

## 5. Behind the scenes (1 min)

- Flask backend, Google Gemini with a JSON schema, validation of every AI answer.
- Security: API key only on the server, strict Content-Security-Policy, rate limiting, no CV text in logs, HTTPS-only deployment config.
- 137 automated tests (pytest, Playwright, axe-core) running in GitHub Actions on every pull request.
- Deployment: AWS EC2, Nginx reverse proxy, Gunicorn, systemd, Let's Encrypt (configuration prepared in `deploy/`).

## Honest status

- Version 1 ran on AWS EC2. Version 2 is finished in GitHub and tested, but **not yet deployed** to the server.
- The real Gemini answers have been tested with fake responses in the automated tests; a real-key check is done with `scripts/gemini_smoke_test.py`.
