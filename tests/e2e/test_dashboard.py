"""Browser tests for the v2.1 interface: upload card, progress view, results dashboard, tablet layout."""
import pytest
from playwright.sync_api import expect

from tests.fakes import FAKE_ANALYSIS
from tests.test_upload import make_docx, make_pdf

pytestmark = pytest.mark.e2e


def run_example(page):
    page.click("#sample-button")
    page.click("#analyze")
    page.wait_for_selector("#results:not([hidden])")


def test_uploaded_file_is_shown_as_a_card(page, tmp_path):
    path = tmp_path / "Alex CV.pdf"
    path.write_bytes(make_pdf(pages=2))
    page.set_input_files("#cv-file", str(path))
    expect(page.locator("#upload-file")).to_be_visible()
    expect(page.locator("#upload-file-name")).to_have_text("Alex CV.pdf")
    expect(page.locator("#upload-file-meta")).to_contain_text("PDF")
    expect(page.locator("#upload-file-meta")).to_contain_text("2 pages")
    expect(page.locator("#upload-empty")).to_be_hidden()


def test_removing_the_file_clears_the_cv(page, tmp_path):
    path = tmp_path / "cv.docx"
    path.write_bytes(make_docx())
    page.set_input_files("#cv-file", str(path))
    expect(page.locator("#upload-file")).to_be_visible()
    page.click("#upload-remove")
    expect(page.locator("#cv")).to_have_value("")
    expect(page.locator("#upload-empty")).to_be_visible()
    expect(page.locator("#upload-button")).to_be_focused()


def test_rejected_upload_keeps_the_empty_upload_area(page, tmp_path):
    path = tmp_path / "fake.pdf"
    path.write_bytes(b"MZ not really a pdf" * 20)
    page.set_input_files("#cv-file", str(path))
    expect(page.locator("#form-alert")).to_contain_text("valid PDF")
    expect(page.locator("#upload-file")).to_be_hidden()
    expect(page.locator("#upload-progress")).to_be_hidden()


def test_progress_view_is_shown_while_waiting(page, slow_ai):
    page.click("#sample-button")
    page.click("#analyze")
    expect(page.locator("#progress")).to_be_visible()
    expect(page.locator("#progress-steps li.is-active")).to_have_count(1)
    expect(page.locator("#progress-steps li").nth(1)).to_have_class("is-active", timeout=5000)
    page.wait_for_selector("#results:not([hidden])", timeout=15000)
    expect(page.locator("#progress")).to_be_hidden()


def test_progress_view_is_hidden_after_an_error(page):
    page.route("**/api/analyze", lambda route: route.fulfill(status=503, json={"error": "Server AI key is not configured."}))
    page.click("#sample-button")
    page.click("#analyze")
    expect(page.locator("#form-alert")).to_contain_text("not configured")
    expect(page.locator("#progress")).to_be_hidden()
    expect(page.locator("#results")).to_be_hidden()


def test_dashboard_counts_match_the_analysis(page):
    run_example(page)
    expect(page.locator("#count-found")).to_have_text(str(len(FAKE_ANALYSIS["matching_skills"])))
    expect(page.locator("#count-missing")).to_have_text(str(len(FAKE_ANALYSIS["missing_skills"])))
    expect(page.locator("#count-suggestions")).to_have_text(str(len(FAKE_ANALYSIS["suggestions"])))
    expect(page.locator("#letter-words")).to_contain_text("words")


def test_suggestions_can_be_ticked_off(page):
    run_example(page)
    boxes = page.locator("#suggestions input[type=checkbox]")
    expect(boxes).to_have_count(len(FAKE_ANALYSIS["suggestions"]))
    page.locator("#suggestions label").first.click()
    expect(boxes.first).to_be_checked()
    expect(page.locator("#suggestions label").first).to_contain_text(FAKE_ANALYSIS["suggestions"][0])


def test_reduced_motion_shows_the_final_score_at_once(page):
    page.emulate_media(reduced_motion="reduce")
    run_example(page)
    assert page.text_content("#score-value") == str(FAKE_ANALYSIS["match_score"])


def test_navigation_links_point_to_real_sections(page):
    for href in page.eval_on_selector_all(".site-nav a", "links => links.map(a => a.getAttribute('href'))"):
        assert page.locator(href).count() == 1, href


def test_tablet_layout_keeps_two_input_columns(browser, base_url):
    context = browser.new_context(viewport={"width": 820, "height": 1180}, is_mobile=True, has_touch=True)
    page = context.new_page()
    page.goto(base_url + "/")
    cv_box, job_box = page.locator("#cv").bounding_box(), page.locator("#job").bounding_box()
    assert abs(cv_box["y"] - job_box["y"]) < 200 and cv_box["x"] < job_box["x"]  # side by side
    page.emulate_media(reduced_motion="reduce")
    run_example(page)
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    context.close()


def test_phone_layout_stacks_the_dashboard(mobile_page):
    mobile_page.emulate_media(reduced_motion="reduce")  # measure the final layout, not the entrance animation
    run_example(mobile_page)
    found = mobile_page.locator(".skills-found").bounding_box()
    missing = mobile_page.locator(".skills-missing").bounding_box()
    assert missing["y"] > found["y"] + found["height"] - 1  # stacked, not side by side
    assert mobile_page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_letter_placeholders_are_highlighted(page):
    run_example(page)
    marks = page.locator("#cover-letter mark")
    expect(marks.first).to_have_text("[Hiring manager]")
    expect(page.locator("#letter-placeholders")).to_contain_text(f"Replace the {marks.count()} highlighted")
    # copying still gives the plain letter text
    assert page.text_content("#cover-letter").startswith("Dear [Hiring manager],")


def test_letter_highlighting_never_creates_html_from_ai_text(page):
    from tests.fakes import FAKE_ANALYSIS as base
    evil = {**base, "score_label": "Partial match",
            "cover_letter": "Dear [<img src=x onerror=window.hacked=1>],\n\nText [Company name]."}
    page.route("**/api/analyze", lambda route: route.fulfill(json={"analysis": evil, "language": "en", "disclaimer": "d"}))
    run_example(page)
    expect(page.locator("#cover-letter mark")).to_have_count(2)
    assert page.locator("#cover-letter img").count() == 0
    assert page.evaluate("window.hacked") is None


def test_every_result_card_is_visible_when_printing(page):
    run_example(page)
    page.emulate_media(media="print")
    opacities = page.eval_on_selector_all("#results .card", "cards => cards.map(c => getComputedStyle(c).opacity)")
    assert opacities and all(o == "1" for o in opacities), opacities
    assert page.locator(".compare").is_hidden() and page.locator(".letter-tips").is_hidden()
