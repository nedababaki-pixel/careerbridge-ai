# Live demo script (about 5 minutes)

A simple script for showing CareerBridge AI in a meeting, presentation or interview.

## Before the demo (10 minutes earlier)

```bash
git checkout main
pip install -r requirements.txt
python scripts/gemini_smoke_test.py      # optional: proves the real Gemini connection works (needs GEMINI_API_KEY in .env)
python app.py                            # open http://127.0.0.1:5055
```

On Windows, double-click `start-windows.bat` instead. Keep the server window open and never press Ctrl+C in it – that stops the server.

- Run one comparison first, so you know Gemini answers today.
- Have a CV (PDF) and a job ad ready.
- Never show the `.env` file or the API key on screen.

## 1. Introduce the demo (20 s)

"Now I will show the app live. It runs on my laptop and uses the real Google Gemini API."

## 2. Upload a CV (40 s)

1. Drag a PDF or DOCX onto **Drop your CV here** (or click **choose a file**).
2. "The text appears in the field, so I can check it before anything is sent. The file is read in memory and never saved. Only PDF and DOCX up to 5 MB are accepted, and the real file content is checked."

Tip: **Try an example** fills in a fictional CV and job ad.

## 3. Paste the job ad and compare (1 min)

1. Paste the job ad.
2. Keep **English**, or choose **Svenska** to show Swedish results.
3. Click **Compare CV and job**. "Now the text goes to Google Gemini. It usually takes about five seconds." Point at the progress view and the **Cancel** button.

## 4. Go through the result (1 min 30 s)

- "The **score** is only an AI estimate, not a hiring decision."
- "**Green** skills are in my CV. **Orange** skills are asked for but missing."
- "The **suggestions** are a checklist I can tick off."

## 5. The cover letter (1 min)

"The placeholders such as [Company name] are highlighted, so I can see what to change. I can copy the letter, download the report, or save it as a PDF with Ctrl + P."

## 6. Finish (10 s)

"Thank you for listening! Do you have any questions?"

## If something goes wrong

| Problem | What to do and say |
|---|---|
| "The AI model is very busy" | "Google's models are sometimes overloaded – that is why the app tries fallback models." Wait a minute and try again |
| "The server could not be reached" | The local server stopped. Run `python app.py` again and reload the page |
| No internet | Show the screenshots in `docs/screenshots/` and the green tests in GitHub Actions |

## Honest status

- 174 automated tests pass in GitHub Actions. Real Gemini answers were verified in English and Swedish on 2026-11-09.
- Version 1 ran on AWS EC2. Version 2 runs locally and is ready for deployment, but is **not yet deployed** to AWS.
