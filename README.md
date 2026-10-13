# CareerBridge AI

An AI-powered CV and job advertisement assistant built with Flask and Google Gemini API.

## Features
- CV vs. job-advertisement analysis
- Skills gap and CV improvement suggestions
- AI-generated cover letter draft
- Responsive web UI
- Server-side API key handling

## Run locally
1. Install Python 3.10+.
2. Run `python -m venv .venv` and activate it.
3. Run `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env` and set your Gemini API key. Never commit `.env`.
5. Run `python app.py` and open `http://127.0.0.1:5000`.

## AWS deployment
Deploy to an EC2 instance created using your Level 3 Terraform infrastructure. For a public deployment, run behind Nginx with a production WSGI server such as Gunicorn, configure security groups and HTTPS, and inject the API key as a server-side secret. Do not expose Flask's development server to the internet. AWS usage can incur charges.

## Security and limitations
Avoid uploading sensitive CV information without consent and a privacy policy. This MVP does not store CV data in a database. The Gemini API provider receives submitted text. Production deployment needs request throttling, abuse prevention, and privacy/legal review.
