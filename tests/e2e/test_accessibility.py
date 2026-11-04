"""Automated accessibility checks with axe-core (WCAG 2.1 A and AA rules)."""
import pytest

axe_module = pytest.importorskip("axe_playwright_python.sync_playwright", reason="axe-playwright-python is not installed")

pytestmark = pytest.mark.e2e

WCAG = {"runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]}}


def violations(page):
    results = axe_module.Axe().run(page, options=WCAG)
    return [f"{v['id']}: {v['help']} ({len(v['nodes'])})" for v in results.response["violations"]]


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_start_page_has_no_axe_violations(page, theme):
    page.emulate_media(color_scheme=theme)
    assert violations(page) == []


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_results_page_has_no_axe_violations(page, theme):
    page.emulate_media(color_scheme=theme)
    page.click("#sample-button")
    page.click("#analyze")
    page.wait_for_selector("#results:not([hidden])")
    page.wait_for_timeout(1000)
    assert violations(page) == []


def test_form_errors_have_no_axe_violations(page):
    page.click("#analyze")
    assert violations(page) == []


def test_progress_view_has_no_axe_violations(page):
    page.route("**/api/analyze", lambda route: None)  # keep the request waiting
    page.click("#sample-button")
    page.click("#analyze")
    page.wait_for_selector("#progress:not([hidden])")
    assert violations(page) == []


def test_uploaded_file_card_has_no_axe_violations(page, tmp_path):
    from tests.test_upload import make_pdf
    path = tmp_path / "cv.pdf"
    path.write_bytes(make_pdf())
    page.set_input_files("#cv-file", str(path))
    page.wait_for_selector("#upload-file:not([hidden])")
    assert violations(page) == []
