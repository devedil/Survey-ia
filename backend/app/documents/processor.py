import io
import re
import unicodedata
import zipfile
from pathlib import Path

from docx import Document as WordDocument
from openpyxl import load_workbook
from pypdf import PdfReader


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".xlsx"}
MAX_ARCHIVE_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_EXTRACTED_CHARACTERS = 2_000_000
DECLARED_MIME_ALIASES = {
    "application/octet-stream",
    "text/plain",
    "text/markdown",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


class DocumentProcessingError(ValueError):
    """Raised when an uploaded document cannot be safely processed."""


def _zip_kind(content: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            total_size = sum(info.file_size for info in archive.infolist())
            if total_size > MAX_ARCHIVE_UNCOMPRESSED_BYTES:
                raise DocumentProcessingError("Compressed document expands beyond the allowed limit")
            names = set(archive.namelist())
            if "word/document.xml" in names and "[Content_Types].xml" in names:
                return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            if "xl/workbook.xml" in names and "[Content_Types].xml" in names:
                return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    except zipfile.BadZipFile as exc:
        raise DocumentProcessingError("Invalid Office document archive") from exc
    raise DocumentProcessingError("Unsupported or malformed Office document")


def detect_mime_type(filename: str, content: bytes, declared_mime: str | None) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise DocumentProcessingError("Unsupported file extension")
    if not content:
        raise DocumentProcessingError("The uploaded file is empty")

    if extension == ".pdf":
        if b"%PDF-" not in content[:1024]:
            raise DocumentProcessingError("File content does not match PDF format")
        detected = "application/pdf"
    elif extension in {".docx", ".xlsx"}:
        detected = _zip_kind(content)
        expected = {
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        }[extension]
        if detected != expected:
            raise DocumentProcessingError("File content does not match its extension")
    else:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentProcessingError("Text documents must use UTF-8 encoding") from exc
        if "\x00" in text:
            raise DocumentProcessingError("Text document contains binary data")
        detected = "text/markdown" if extension == ".md" else "text/plain"

    normalized_declared = (declared_mime or "").split(";", 1)[0].strip().lower()
    if normalized_declared and normalized_declared not in DECLARED_MIME_ALIASES:
        raise DocumentProcessingError("Declared MIME type is not supported")
    if normalized_declared not in {"", "application/octet-stream", detected}:
        if not (detected in {"text/plain", "text/markdown"} and normalized_declared in {"text/plain", "text/markdown"}):
            raise DocumentProcessingError("Declared MIME type does not match file content")
    return detected


def _clean_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).replace("\r\n", "\n").replace("\r", "\n")
    normalized = "".join(
        char for char in normalized
        if char in "\n\t" or not unicodedata.category(char).startswith("C")
    )
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def extract_text(filename: str, content: bytes) -> str:
    extension = Path(filename).suffix.lower()
    try:
        if extension in {".txt", ".md"}:
            text = content.decode("utf-8-sig")
        elif extension == ".pdf":
            reader = PdfReader(io.BytesIO(content), strict=True)
            text = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        elif extension == ".docx":
            document = WordDocument(io.BytesIO(content))
            parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
            for table in document.tables:
                for row in table.rows:
                    parts.append(" | ".join(cell.text.strip() for cell in row.cells))
            text = "\n".join(parts)
        elif extension == ".xlsx":
            workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            try:
                if len(workbook.worksheets) > 50:
                    raise DocumentProcessingError("Workbook contains too many worksheets")
                parts = []
                for sheet in workbook.worksheets:
                    parts.append(f"Sheet: {sheet.title}")
                    for row_number, row in enumerate(
                        sheet.iter_rows(max_row=20_000, max_col=200, values_only=True),
                        start=1,
                    ):
                        values = [str(value).strip() if value is not None else "" for value in row[:200]]
                        if any(values):
                            parts.append(" | ".join(values))
                text = "\n".join(parts)
            finally:
                workbook.close()
        else:
            raise DocumentProcessingError("Unsupported file extension")
    except DocumentProcessingError:
        raise
    except Exception as exc:
        raise DocumentProcessingError(f"Unable to extract text from {extension} document") from exc

    cleaned = _clean_text(text)
    if not cleaned:
        raise DocumentProcessingError("No extractable text was found in the document")
    if len(cleaned) > MAX_EXTRACTED_CHARACTERS:
        raise DocumentProcessingError("Extracted document text exceeds the allowed limit")
    return cleaned
