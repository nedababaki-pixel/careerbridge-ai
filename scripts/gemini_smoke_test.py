"""Check the REAL Gemini integration once, with your own API key.

Usage (from the project folder, with GEMINI_API_KEY in .env or the environment):
    python scripts/gemini_smoke_test.py

It sends the built-in fictional example CV and job ad through the app's own
/api/analyze endpoint, once in English and once in Swedish, and prints a short
summary. It never prints the API key. Each run makes two Gemini requests.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as app_module  # noqa: E402  (loads .env)

CV = """Alex Lindqvist (fictional example). IT Operations Technician student, Stockholm.
Internship in IT support 2026: answered user tickets, reset passwords and managed accounts in Active Directory,
installed Windows 11 laptops. Skills: Windows Server, Active Directory, Group Policy, DNS, DHCP, Linux basics,
AWS EC2 (course labs), Terraform basics, VLANs and OSPF in Cisco Packet Tracer. English fluent, Swedish intermediate."""

JOB = """Junior IT Technician – Service Desk (fictional example), Stockholm. Help colleagues with IT issues by phone,
chat and on site. Manage user accounts in Active Directory and Microsoft 365. Set up laptops and printers.
Document solutions in our knowledge base. Requirements: IT education, Windows 10/11, Active Directory.
A plus: Microsoft 365 / Intune, ITIL Foundation. Good communication in Swedish and English."""


def main() -> int:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if key.lower() in app_module.PLACEHOLDER_KEYS:
        print("GEMINI_API_KEY is not set. Add it to .env first (never commit .env).")
        return 2
    print(f"Model: {os.getenv('GEMINI_MODEL', 'gemini-3.8-flash')}  (key found, not shown)")
    app_module.limiter.enabled = False
    client = app_module.app.test_client()
    ok = True
    for language in ("en", "sv"):
        started = time.monotonic()
        response = client.post("/api/analyze", json={"cv": CV, "job": JOB, "language": language})
        seconds = time.monotonic() - started
        body = response.get_json(silent=True) or {}
        if response.status_code != 200:
            ok = False
            print(f"[{language}] FAILED: HTTP {response.status_code} – {body.get('error')} ({seconds:.1f} s)")
            continue
        a = body["analysis"]
        print(f"[{language}] OK in {seconds:.1f} s: score {a['match_score']}% ({a['score_label']}), "
              f"{len(a['matching_skills'])} found, {len(a['missing_skills'])} missing, "
              f"{len(a['suggestions'])} suggestions, cover letter {len(a['cover_letter'].split())} words")
        print(f"     summary: {a['summary'][:160]}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
