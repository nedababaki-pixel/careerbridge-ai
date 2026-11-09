"""Browser tests for the CareerBridge AI interface (Playwright + Chromium)."""
import json
import re

import pytest
from playwright.sync_api import expect

from tests.fakes import FAKE_ANALYSIS
from tests.test_upload import make_docx, make_pdf

pytestmark = pytest.mark.e2e


def submit_example(page):
    page.click("#sample-button")
    page.click("#analyze")


def run_example(page):
    submit_example(page)
    page.wait_for_selector("#results:not([hidden])")


def test_page_loads_without_errors(page):
    assert "CareerBridge AI" in page.title()
    assert page.is_visible("h1")
    assert page.errors == []


def test_empty_form_is_validated_in_the_browser(page):
    requests = []
    page.on("request", lambda r: "/api/analyze" in r.url and requests.append(r))
    page.click("#analyze")
    assert page.is_visible("#cv-error") and page.is_visible("#job-error")
    assert page.get_attribute("#cv", "aria-invalid") == "true"
    assert page.evaluate("document.activeElement.id") == "cv"
    page.wait_for_timeout(300)
    assert requests == []


def test_character_counter_updates(page):
    page.fill("#cv", "a" * 1234)
    assert page.text_content("#cv-count").startswith("1,234")


def test_full_comparison_shows_structured_results(page):
    run_example(page)
    expect(page.locator("#score-value")).to_have_text(str(FAKE_ANALYSIS["match_score"]))  # after the count-up animation
    assert page.text_content("#score-label") == "Partial match"
    assert "AI estimate" in page.text_content("#score-text")
    assert "not a prediction" in page.text_content("#disclaimer")
    assert page.locator("#matching-skills li").count() == len(FAKE_ANALYSIS["matching_skills"])
    assert page.locator("#missing-skills li").count() == len(FAKE_ANALYSIS["missing_skills"])
    assert page.locator("#suggestions li").count() == len(FAKE_ANALYSIS["suggestions"])
    assert "Dear [Hiring manager]" in page.text_content("#cover-letter")
    assert page.errors == []


def test_ai_text_is_inserted_as_text_not_html(page):
    evil = {**FAKE_ANALYSIS, "summary": '<img src=x onerror="window.hacked=1">Summary'}
    page.route("**/api/analyze", lambda route: route.fulfill(json={"analysis": {**evil, "score_label": "Partial match"},
                                                                    "language": "en", "disclaimer": "d"}))
    run_example(page)
    assert page.locator("#summary img").count() == 0
    assert page.evaluate("window.hacked") is None


def test_swedish_output_language_is_sent(page):
    page.select_option("#language", "sv")
    with page.expect_request("**/api/analyze") as request:
        run_example(page)
    assert json.loads(request.value.post_data)["language"] == "sv"
    assert page.get_attribute("#results", "lang") == "sv"


def test_pdf_upload_fills_the_cv_field(page, tmp_path):
    path = tmp_path / "cv.pdf"
    path.write_bytes(make_pdf())
    page.set_input_files("#cv-file", str(path))
    expect(page.locator("#cv")).to_have_value(re.compile("Active Directory"))
    assert "cv.pdf" in page.text_content("#form-status")


def test_docx_upload_fills_the_cv_field(page, tmp_path):
    path = tmp_path / "cv.docx"
    path.write_bytes(make_docx())
    page.set_input_files("#cv-file", str(path))
    expect(page.locator("#cv")).to_have_value(re.compile("Nginx"))


def test_unsupported_file_shows_a_clear_message(page, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("hello")
    page.set_input_files("#cv-file", str(path))
    expect(page.locator("#form-alert")).to_contain_text("Only PDF and DOCX")


def test_proxy_error_page_gives_a_helpful_message(page):
    # Nginx returns an HTML page (not JSON) when Gunicorn is down. The original app showed "Connection error".
    page.route("**/api/analyze", lambda route: route.fulfill(status=502, content_type="text/html",
                                                             body="<html>502 Bad Gateway</html>"))
    submit_example(page)
    expect(page.locator("#form-alert")).to_contain_text("could not reach the AI service")
    assert page.is_hidden("#results")


def test_server_error_message_is_shown(page):
    page.route("**/api/analyze", lambda route: route.fulfill(status=429, json={"error": "Too many requests. Please wait a minute and try again."}))
    submit_example(page)
    expect(page.locator("#form-alert")).to_contain_text("Too many requests")


def test_comparison_can_be_cancelled(page):
    page.route("**/api/analyze", lambda route: None)  # never answers
    page.click("#sample-button")
    page.click("#analyze")
    page.wait_for_selector("#cancel-button:not([hidden])")
    assert page.is_disabled("#analyze")
    page.click("#cancel-button")
    expect(page.locator("#analyze")).to_be_enabled()
    expect(page.locator("#form-status")).to_contain_text("cancelled")


def test_cover_letter_can_be_copied(page):
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    run_example(page)
    page.click("#copy-letter")
    expect(page.locator("#copy-letter")).to_have_text("Copied")
    assert page.evaluate("navigator.clipboard.readText()").startswith("Dear [Hiring manager]")


def test_report_can_be_downloaded(page, tmp_path):
    run_example(page)
    with page.expect_download() as download:
        page.click("#download-report")
    saved = tmp_path / "report.txt"
    download.value.save_as(saved)
    text = saved.read_text(encoding="utf-8")
    assert "Match score (AI estimate): 68%" in text and "COVER LETTER DRAFT" in text


def test_theme_choice_is_remembered(page):
    page.click("#theme-toggle")
    first = page.evaluate("document.documentElement.dataset.theme")
    page.reload()
    assert page.evaluate("document.documentElement.dataset.theme") == first


def test_clear_resets_everything(page):
    run_example(page)
    page.click("#clear-button")
    assert page.input_value("#cv") == "" and page.input_value("#job") == ""
    assert page.is_hidden("#results")


def test_skip_link_is_the_first_focus_target(page):
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.className") == "skip-link"


def test_mobile_layout_has_no_horizontal_scroll(mobile_page):
    run_example(mobile_page)
    assert mobile_page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    box = mobile_page.locator("#analyze").bounding_box()
    assert box["width"] > 300  # full-width primary button on phones
