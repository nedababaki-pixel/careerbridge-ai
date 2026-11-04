"""CareerBridge AI: compare a CV with a job advertisement using the Google Gemini API."""
import io
import logging
import os
import re
import time

import requests
from dotenv import load_dotenv
from flask import Flask, Request, jsonify, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

import analysis
import cv_extract

load_dotenv()

__version__ = "2.1.0"

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("careerbridge")

# ---------- limits and settings ----------
MIN_CHARS = 30
MAX_CHARS = 12_000
MAX_UPLOAD_BYTES = 5 * 1024 * 1024          # largest CV file accepted
MAX_REQUEST_BYTES = 6 * 1024 * 1024         # whole request, including form overhead
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_CONNECT_TIMEOUT = 10
GEMINI_READ_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT", "90"))  # keep below Gunicorn's timeout (120 s)
PLACEHOLDER_KEYS = {"", "replace_with_your_key", "your_api_key", "changeme"}
MODEL_NAME = re.compile(r"^[A-Za-z0-9._-]{1,100}$")

CONTENT_SECURITY_POLICY = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
    "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
)


class InMemoryRequest(Request):
    """Keep uploaded files in memory so CV files are never written to a temporary file on disk."""

    def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
        return io.BytesIO()


app = Flask(__name__)
app.request_class = InMemoryRequest
app.config.update(
    MAX_CONTENT_LENGTH=MAX_REQUEST_BYTES,
    SEND_FILE_MAX_AGE_DEFAULT=86400,  # static files carry ?v=<version>, so a day of caching is safe
)

# Behind Nginx, trust one proxy for the client IP and the original scheme (http/https).
if os.getenv("TRUST_PROXY", "0") == "1":
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=os.getenv("RATELIMIT_STORAGE_URI", "memory://"),
    headers_enabled=True,
)
ANALYZE_LIMIT = os.getenv("RATE_LIMIT_ANALYZE", "5 per minute;50 per day")
UPLOAD_LIMIT = os.getenv("RATE_LIMIT_UPLOAD", "10 per minute")


def api_error(message: str, status: int):
    return jsonify(error=message), status


# ---------- security headers and error handling ----------

@app.after_request
def add_security_headers(response):
    headers = response.headers
    headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("X-Frame-Options", "DENY")
    headers.setdefault("Referrer-Policy", "no-referrer")
    headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if request.is_secure:
        headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if request.path.startswith("/api/"):
        headers["Cache-Control"] = "no-store"  # never cache CV text or analysis results
    return response


FRIENDLY_ERRORS = {
    400: "The request could not be read.",
    404: "This address does not exist.",
    405: "This method is not allowed here.",
    413: "The request is too large. CV files can be at most 5 MB.",
    429: "Too many requests. Please wait a minute and try again.",
}


@app.errorhandler(HTTPException)
def handle_http_error(error):
    if request.path.startswith("/api/"):
        return api_error(FRIENDLY_ERRORS.get(error.code, error.name), error.code)
    return error


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    log.exception("Unexpected error on %s %s", request.method, request.path)
    if request.path.startswith("/api/"):
        return api_error("Something went wrong on the server. Please try again.", 500)
    return "Internal Server Error", 500


# ---------- pages ----------

@app.get("/")
def home():
    return render_template("index.html", version=__version__, max_chars=MAX_CHARS, min_chars=MIN_CHARS)


@app.get("/health")
@limiter.exempt
def health():
    return jsonify(status="ok")


# ---------- API ----------

@app.post("/api/extract-cv")
@limiter.limit(lambda: UPLOAD_LIMIT)
def extract_cv():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return api_error("Choose a PDF or DOCX file to upload.", 400)
    data = upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return api_error(FRIENDLY_ERRORS[413], 413)
    try:
        cv = cv_extract.extract_cv(upload.filename, data)
    except cv_extract.ExtractionError as exc:
        log.info("CV upload rejected: %s (%s)", exc.message, exc.status)
        return api_error(exc.message, exc.status)
    finally:
        del data
    truncated = len(cv.text) > MAX_CHARS
    text = cv.text[:MAX_CHARS]
    log.info("CV extracted: type=%s pages=%s chars=%d truncated=%s", cv.file_type, cv.pages, len(text), truncated)
    return jsonify(text=text, characters=len(text), truncated=truncated, file_type=cv.file_type, pages=cv.pages)


@app.post("/api/analyze")
@limiter.limit(lambda: ANALYZE_LIMIT)
def analyze():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return api_error("Send a JSON object with 'cv' and 'job' text fields.", 400)
    cv, job = data.get("cv", ""), data.get("job", "")
    if not isinstance(cv, str) or not isinstance(job, str):
        return api_error("The CV and the job advertisement must be sent as text.", 400)
    cv, job = cv.strip(), job.strip()
    if len(cv) < MIN_CHARS or len(job) < MIN_CHARS:
        return api_error(f"Please enter at least {MIN_CHARS} characters in both fields.", 400)
    if len(cv) > MAX_CHARS or len(job) > MAX_CHARS:
        return api_error(f"Text is too long (maximum {MAX_CHARS:,} characters per field).", 400)
    language = data.get("language", "en")
    if language not in analysis.LANGUAGES:
        return api_error("Unsupported output language. Choose 'en' or 'sv'.", 400)

    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key.lower() in PLACEHOLDER_KEYS:
        return api_error("Server AI key is not configured.", 503)
    model = os.getenv("GEMINI_MODEL", analysis.DEFAULT_MODEL).strip() or analysis.DEFAULT_MODEL
    if not MODEL_NAME.match(model):
        log.error("GEMINI_MODEL contains invalid characters")
        return api_error("Server AI model is not configured correctly.", 503)

    started = time.monotonic()
    try:
        response = requests.post(
            GEMINI_URL.format(model=model),
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            json=analysis.build_request(cv, job, language),
            timeout=(GEMINI_CONNECT_TIMEOUT, GEMINI_READ_TIMEOUT),
        )
    except requests.Timeout:
        log.warning("Gemini timed out after %.1f s", time.monotonic() - started)
        return api_error("The AI service took too long to respond. Please try again.", 504)
    except requests.RequestException as exc:
        log.warning("Gemini request failed: %s", type(exc).__name__)
        return api_error("AI service is unavailable. Check your API configuration or try again.", 502)

    if not response.ok:
        # The error body is not logged: it is not needed and could contain request details.
        log.warning("Gemini returned HTTP %s", response.status_code)
        if response.status_code == 429:
            return api_error("The AI service is busy (quota or rate limit reached). Please try again later.", 503)
        return api_error("AI service is unavailable. Check your API configuration or try again.", 502)

    try:
        body = response.json()
    except ValueError:
        log.warning("Gemini returned a non-JSON body")
        return api_error("AI service is unavailable. Check your API configuration or try again.", 502)

    if analysis.is_blocked(body):
        log.info("Gemini blocked the request (safety filter)")
        return api_error("The AI could not analyse this text. Please check the content and try again.", 422)

    try:
        answer = analysis.extract_text(body)
    except analysis.AnalysisError:
        log.warning("Gemini response had an unexpected structure")
        return api_error("AI service is unavailable. Check your API configuration or try again.", 502)
    if not answer.strip():
        return api_error("AI returned an empty answer. Try again.", 502)

    try:
        result = analysis.parse_result(answer)
    except analysis.AnalysisError as exc:
        log.warning("Gemini answer rejected: %s", exc)
        return api_error("The AI answer was incomplete. Please try again.", 502)

    log.info("Analysis done: model=%s language=%s score=%d duration=%.1fs",
             model, language, result["match_score"], time.monotonic() - started)
    return jsonify(analysis=result, language=language, disclaimer=analysis.DISCLAIMER)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5055")), debug=False)
