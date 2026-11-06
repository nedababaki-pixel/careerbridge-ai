"""Extract plain text from an uploaded CV (PDF or DOCX).

Security notes:
- Files are processed in memory only and are never written to disk.
- The file type is checked twice: by extension and by the file's actual
  content ("magic bytes"), so a renamed .exe is rejected.
- PDFs are limited by page count; encrypted PDFs are rejected.
- DOCX files are ZIP archives, so the number of entries and the total
  uncompressed size are limited to stop "zip bombs". python-docx parses XML
  with entity resolution disabled, so XXE payloads are not expanded.
"""
import io
import re
import zipfile
from dataclasses import dataclass

MAX_PDF_PAGES = 20
MAX_ZIP_ENTRIES = 500
MAX_DOCX_UNCOMPRESSED_BYTES = 30 * 1024 * 1024
MIN_TEXT_CHARS = 30

ALLOWED_EXTENSIONS = {".pdf": "pdf", ".docx": "docx"}


class ExtractionError(Exception):
    """The file cannot be used. `status` is the HTTP status code to return."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class ExtractedCV:
    text: str
    file_type: str
    pages: int | None = None


def _extension(filename: str) -> str:
    match = re.search(r"(\.[A-Za-z0-9]+)$", filename or "")
    return match.group(1).lower() if match else ""


def detect_type(filename: str, data: bytes) -> str:
    file_type = ALLOWED_EXTENSIONS.get(_extension(filename))
    if file_type is None:
        raise ExtractionError("Only PDF and DOCX files are supported.", 415)
    if file_type == "pdf" and not data.startswith(b"%PDF-"):
        raise ExtractionError("This file does not look like a valid PDF.", 415)
    if file_type == "docx":
        if not zipfile.is_zipfile(io.BytesIO(data)):
            raise ExtractionError("This file does not look like a valid DOCX document.", 415)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
        if "word/document.xml" not in names or "[Content_Types].xml" not in names:
            raise ExtractionError("This file does not look like a valid DOCX document.", 415)
    return file_type


def _normalise(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _extract_pdf(data: bytes) -> ExtractedCV:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ExtractionError("Password-protected PDFs are not supported. Please upload an unprotected file.", 422)
        page_count = len(reader.pages)
        if page_count > MAX_PDF_PAGES:
            raise ExtractionError(f"The PDF has {page_count} pages. The limit is {MAX_PDF_PAGES} pages.", 422)
        text = "\n".join((page.extract_text() or "") for page in reader.pages)
    except ExtractionError:
        raise
    except (PdfReadError, ValueError, KeyError, TypeError, OSError, RecursionError) as exc:
        raise ExtractionError("The PDF could not be read. It may be damaged.", 422) from exc
    return ExtractedCV(_normalise(text), "pdf", page_count)


def _extract_docx(data: bytes) -> ExtractedCV:
    import docx

    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > MAX_DOCX_UNCOMPRESSED_BYTES:
            raise ExtractionError("The DOCX file is too large when unpacked.", 422)
    try:
        document = docx.Document(io.BytesIO(data))
        lines = [p.text for p in document.paragraphs]
        for table in document.tables:
            for row in table.rows:
                cells = []
                for cell in row.cells:
                    if cell.text and cell.text not in cells:  # merged cells repeat their text
                        cells.append(cell.text)
                lines.append(" | ".join(cells))
    except ExtractionError:
        raise
    except Exception as exc:  # python-docx raises many different errors for broken files
        raise ExtractionError("The DOCX file could not be read. It may be damaged.", 422) from exc
    return ExtractedCV(_normalise("\n".join(lines)), "docx")


def extract_cv(filename: str, data: bytes) -> ExtractedCV:
    file_type = detect_type(filename, data)
    result = _extract_pdf(data) if file_type == "pdf" else _extract_docx(data)
    if len(result.text) < MIN_TEXT_CHARS:
        raise ExtractionError(
            "No readable text was found in the file. If it is a scanned image, please paste the text instead.", 422
        )
    return result
