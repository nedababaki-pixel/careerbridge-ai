"""Tests for CV upload and text extraction (/api/extract-cv and cv_extract.py).

Real PDF and DOCX files are created in memory for each test, including
broken and malicious files (renamed executables, zip bombs, XXE payloads).
"""
import io
import tempfile
import zipfile
from unittest.mock import patch

import docx
import pytest
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

import app as app_module
import cv_extract

CV_LINES = ["Alex Lindqvist (fictional)", "IT Operations Technician student",
            "Skills: Active Directory, Windows Server, AWS EC2, Linux, Nginx"]


@pytest.fixture
def client():
    app_module.limiter.enabled = False
    with app_module.app.test_client() as c:
        yield c
    app_module.limiter.enabled = True


def make_pdf(pages=1, lines=CV_LINES, text=True) -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for _ in range(pages):
        if text:
            y = 800
            for line in lines:
                pdf.drawString(72, y, line)
                y -= 18
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def make_docx(paragraphs=CV_LINES, table=None) -> bytes:
    document = docx.Document()
    for p in paragraphs:
        document.add_paragraph(p)
    if table:
        t = document.add_table(rows=len(table), cols=len(table[0]))
        for r, row in enumerate(table):
            for c, value in enumerate(row):
                t.cell(r, c).text = value
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def upload(client, data: bytes, name: str):
    return client.post("/api/extract-cv", data={"file": (io.BytesIO(data), name)},
                       content_type="multipart/form-data")


# ---------- happy paths ----------

def test_pdf_text_is_extracted(client):
    r = upload(client, make_pdf(pages=2), "cv.pdf")
    assert r.status_code == 200
    body = r.get_json()
    assert "Active Directory" in body["text"] and body["file_type"] == "pdf" and body["pages"] == 2
    assert r.headers["Cache-Control"] == "no-store"


def test_docx_text_including_tables_is_extracted(client):
    r = upload(client, make_docx(table=[["Skill", "Level"], ["Terraform", "Basic"]]), "My CV.DOCX")
    assert r.status_code == 200
    text = r.get_json()["text"]
    assert "IT Operations Technician student" in text and "Terraform | Basic" in text


def test_long_cv_is_truncated_to_the_text_limit(client):
    paragraphs = [f"Line {i}: " + "experience with Linux servers and AWS. " * 4 for i in range(200)]
    body = upload(client, make_docx(paragraphs), "long.docx").get_json()
    assert body["truncated"] is True and body["characters"] == app_module.MAX_CHARS


def test_uploads_are_not_written_to_temporary_files(client):
    data = make_pdf(pages=3) + b"\n%" + b"x" * (1024 * 1024)  # > 500 KB, Werkzeug's normal spill-to-disk size
    with patch.object(tempfile, "SpooledTemporaryFile", side_effect=AssertionError("disk used")), \
         patch.object(tempfile, "TemporaryFile", side_effect=AssertionError("disk used")), \
         patch.object(tempfile, "NamedTemporaryFile", side_effect=AssertionError("disk used")):
        r = upload(client, data, "cv.pdf")
    assert r.status_code == 200


# ---------- rejected files ----------

def test_missing_file_is_rejected(client):
    r = client.post("/api/extract-cv", data={}, content_type="multipart/form-data")
    assert r.status_code == 400 and "Choose a PDF or DOCX" in r.get_json()["error"]


@pytest.mark.parametrize("name", ["cv.txt", "cv.exe", "cv.pdf.exe", "cv", "cv.doc"])
def test_unsupported_extensions_are_rejected(client, name):
    assert upload(client, make_pdf(), name).status_code == 415


@pytest.mark.parametrize("data, name", [(b"MZ\x90\x00" + b"\x00" * 200, "cv.pdf"),   # Windows executable renamed
                                        (b"%PDF-" * 0 + b"hello world" * 10, "cv.pdf"),
                                        (make_pdf(), "cv.docx"),                      # PDF renamed to .docx
                                        (b"PK\x03\x04 not really a zip", "cv.docx")])
def test_files_with_wrong_content_are_rejected(client, data, name):
    assert upload(client, data, name).status_code == 415


def test_damaged_pdf_is_rejected(client):
    r = upload(client, b"%PDF-1.7\n" + b"\x00garbage" * 50, "cv.pdf")
    assert r.status_code == 422 and r.is_json


def test_password_protected_pdf_is_rejected(client):
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(make_pdf())))
    writer.encrypt(user_password="secret", owner_password="owner")
    buffer = io.BytesIO()
    writer.write(buffer)
    r = upload(client, buffer.getvalue(), "cv.pdf")
    assert r.status_code == 422 and "Password-protected" in r.get_json()["error"]


def test_too_many_pages_are_rejected(client):
    r = upload(client, make_pdf(pages=cv_extract.MAX_PDF_PAGES + 1), "cv.pdf")
    assert r.status_code == 422 and "pages" in r.get_json()["error"]


def test_scanned_pdf_without_text_gets_a_helpful_message(client):
    r = upload(client, make_pdf(text=False), "scan.pdf")
    assert r.status_code == 422 and "scanned" in r.get_json()["error"]


def test_file_over_5_mb_is_rejected(client):
    data = make_pdf() + b"\n%" + b"x" * (5 * 1024 * 1024)
    r = upload(client, data, "big.pdf")
    assert r.status_code == 413 and r.is_json


def test_zip_bomb_docx_is_rejected(client):
    original = zipfile.ZipFile(io.BytesIO(make_docx()))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bomb:
        for item in original.infolist():
            bomb.writestr(item, original.read(item.filename))
        bomb.writestr("word/media/huge.bin", b"\x00" * (40 * 1024 * 1024))  # 40 MB unpacked, ~40 KB packed
    assert len(buffer.getvalue()) < 1024 * 1024
    r = upload(client, buffer.getvalue(), "cv.docx")
    assert r.status_code == 422 and "too large when unpacked" in r.get_json()["error"]


def test_xxe_payload_in_docx_is_not_expanded(client, tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("TOP-SECRET-SERVER-FILE")
    original = zipfile.ZipFile(io.BytesIO(make_docx()))
    document_xml = original.read("word/document.xml").decode()
    evil = document_xml.replace(
        "<w:document", f'<!DOCTYPE w:document [<!ENTITY xxe SYSTEM "file://{secret}">]><w:document', 1
    ).replace("IT Operations Technician student", "IT Operations Technician student &xxe;", 1)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as out:
        for item in original.infolist():
            content = evil.encode() if item.filename == "word/document.xml" else original.read(item.filename)
            out.writestr(item, content)
    r = upload(client, buffer.getvalue(), "cv.docx")
    assert "TOP-SECRET-SERVER-FILE" not in r.get_data(as_text=True)
