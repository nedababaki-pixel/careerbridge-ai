"""A realistic fake Gemini answer used by the browser tests and the screenshot script.

No real API is called. The content is fictional and matches the built-in example CV and job ad.
"""
import json
from unittest.mock import MagicMock

FAKE_ANALYSIS = {
    "match_score": 68,
    "score_explanation": "The CV shows most of the core service desk skills, but Microsoft 365, Intune and ITIL are not mentioned.",
    "summary": "A solid junior profile for a service desk role. Hands-on Active Directory and laptop setup from the internship match the daily tasks well. Adding Microsoft 365 experience and documenting your support work would make the application stronger.",
    "matching_skills": ["Active Directory", "Windows 11", "User account management", "IT support tickets",
                        "IT education", "English"],
    "missing_skills": ["Microsoft 365", "Intune", "ITIL Foundation", "Knowledge base documentation",
                       "Fluent Swedish"],
    "suggestions": [
        "Describe the volume and type of tickets you handled during the internship, for example per week.",
        "Mention any Microsoft 365 administration you did in courses or the internship, if you did it.",
        "Add a short line about how you documented solutions, since the role asks for knowledge base work.",
        "List your Swedish level honestly and mention that you are studying to improve it.",
    ],
    "cover_letter": "Dear [Hiring manager],\n\nI am applying for the Junior IT Technician role at [Company name]. "
                    "During my IT Operations Technician studies and my internship in IT support, I helped users by "
                    "phone and through a ticket system, managed accounts in Active Directory and prepared Windows 11 "
                    "laptops for new employees.\n\nI enjoy solving problems for colleagues and explaining solutions "
                    "clearly. I have not yet worked with Intune, but I learn new tools quickly and would welcome the "
                    "chance to develop in your team.\n\nKind regards,\n[Your name]",
}


def fake_response(analysis=None, status=200):
    resp = MagicMock()
    resp.ok = status < 400
    resp.status_code = status
    resp.json.return_value = {"candidates": [{"content": {"parts": [
        {"text": "thinking...", "thought": True},
        {"text": json.dumps(analysis or FAKE_ANALYSIS)},
    ]}, "finishReason": "STOP"}]}
    return resp
