"""Fast diagnosis of the Gemini connection (each check has a short timeout).

Usage (from the project folder, with GEMINI_API_KEY in .env):
    python scripts/gemini_diagnose.py
    python scripts/gemini_diagnose.py --model gemini-3.6-flash     # try another model

Checks, in order:
  1. Key and access: list the models this key can use (no generation, free).
  2. The configured model exists for this key.
  3. A tiny text answer without extra settings.
  4. The same tiny answer with thinking level "low".
  5. The real CareerBridge request (JSON schema) with thinking level "low".
  6. The real CareerBridge request with the model's default thinking (only with --full).

Checks 3-6 make small paid/quota requests (5 at most). The API key is never printed.
"""
import argparse
import os
import sys
import time

import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import analysis  # noqa: E402

BASE = "https://generativelanguage.googleapis.com/v1beta"
CV = "IT Operations Technician student. Internship in IT support: Active Directory, Windows 11 laptops, user tickets."
JOB = "Junior IT Technician, service desk. Requirements: Active Directory, Windows 11, Microsoft 365, ITIL is a plus."


def redact(text: str, key: str) -> str:
    return text.replace(key, "<key>") if key else text


def call(method, url, key, timeout, body=None):
    started = time.monotonic()
    try:
        response = requests.request(method, url, headers={"x-goog-api-key": key, "Content-Type": "application/json"},
                                    json=body, timeout=(10, timeout))
    except requests.Timeout:
        return None, None, time.monotonic() - started, f"TIMEOUT (no answer within {timeout} s)"
    except requests.RequestException as exc:
        return None, None, time.monotonic() - started, f"NETWORK ERROR: {type(exc).__name__}"
    seconds = time.monotonic() - started
    try:
        data = response.json()
    except ValueError:
        data = None
    error = ""
    if not response.ok:
        message = (data or {}).get("error", {}).get("message", response.text[:200]) if isinstance(data, dict) else response.text[:200]
        error = redact(str(message), key)[:300]
    return response.status_code, data, seconds, error


def describe_answer(data):
    if not isinstance(data, dict):
        return ""
    usage = data.get("usageMetadata", {})
    candidate = (data.get("candidates") or [{}])[0]
    return (f"finish={candidate.get('finishReason', '?')}, thinking tokens={usage.get('thoughtsTokenCount', 0)}, "
            f"answer tokens={usage.get('candidatesTokenCount', 0)}")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", analysis.DEFAULT_MODEL).strip() or analysis.DEFAULT_MODEL)
    parser.add_argument("--timeout", type=int, default=45, help="seconds per generation check (default 45)")
    parser.add_argument("--full", action="store_true", help="also test the model's default thinking level (slow)")
    args = parser.parse_args()

    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key or key == "replace_with_your_key":
        print("GEMINI_API_KEY is missing in .env.")
        return 2
    print(f"Key found (length {len(key)}, not shown). Model under test: {args.model}\n")

    # 1. Key and access
    status, data, seconds, error = call("GET", f"{BASE}/models?pageSize=1000", key, 15)
    if status != 200:
        print(f"1. Key/access  FAIL  HTTP {status} in {seconds:.1f} s  {error}")
        print("   -> The key is not accepted or the API is not enabled for its Google project.")
        return 1
    names = [m.get("name", "").removeprefix("models/") for m in data.get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    flash = sorted(n for n in names if "flash" in n)
    print(f"1. Key/access  OK    {len(names)} models available in {seconds:.1f} s")
    print(f"   Flash models for this key: {', '.join(flash) or '(none)'}")

    # 2. Model exists
    if args.model in names:
        print(f"2. Model       OK    {args.model} is available for this key")
    else:
        print(f"2. Model       FAIL  {args.model} is NOT available for this key -> choose one of the Flash models above")
        return 1

    url = f"{BASE}/models/{args.model}:generateContent"
    tiny = {"contents": [{"role": "user", "parts": [{"text": "Answer with the single word: OK"}]}]}
    low = analysis.thinking_config(args.model, "low")
    real = analysis.build_request(CV * 3, JOB * 2, "en", thinking_level="low", model=args.model)
    checks = [
        ("3. Tiny answer, default thinking", tiny),
        ("4. Tiny answer, thinking low    ", {**tiny, "generationConfig": {"thinkingConfig": low}}),
        ("5. CareerBridge JSON, thinking low", real),
    ]
    if args.full:
        checks.append(("6. CareerBridge JSON, default thinking",
                       analysis.build_request(CV * 3, JOB * 2, "en", thinking_level=None, model=args.model)))

    worked = {}
    for label, body in checks:
        status, data, seconds, error = call("POST", url, key, args.timeout, body)
        ok = status == 200
        worked[label[0]] = ok
        detail = describe_answer(data) if ok else (error or f"HTTP {status}")
        print(f"{label}  {'OK  ' if ok else 'FAIL'}  {seconds:5.1f} s  {detail}")
        if label.startswith("5") and ok:
            try:
                result = analysis.parse_result(analysis.extract_text(data))
                print(f"   Parsed: score {result['match_score']}% ({result['score_label']}), "
                      f"{len(result['matching_skills'])} found, {len(result['missing_skills'])} missing")
            except analysis.AnalysisError as exc:
                print(f"   The answer could not be parsed: {exc}")
                worked["5"] = False

    print()
    if worked.get("5"):
        print("RESULT: Gemini works with thinking level 'low'. Keep GEMINI_THINKING_LEVEL=low and run scripts/gemini_smoke_test.py.")
    elif worked.get("4") and not worked.get("5"):
        print("RESULT: The model answers, but the full JSON request is too slow or fails. Try: --model gemini-3.6-flash")
    elif not worked.get("3") and not worked.get("4"):
        print("RESULT: Even a one-word answer fails for this model. Try another model, e.g. --model gemini-3.6-flash")
    else:
        print("RESULT: Mixed results - send this output for analysis.")
    return 0 if worked.get("5") else 1


if __name__ == "__main__":
    sys.exit(main())
