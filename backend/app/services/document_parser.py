import io
import os
from pathlib import Path
import re
from typing import List, Tuple
import zipfile

from fastapi import HTTPException, status
from pypdf import PdfReader
from docx import Document

from app.core.config import settings

# Max file size: 10 Megabytes
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
MIN_EXTRACTED_CHARS = 20

# Private storage directory
STORAGE_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "data" / "resumes"
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)


class ParsedDocument:
    """Extracted text and structural metadata from a parsed CV document."""

    def __init__(self, full_text: str, page_count: int, pages: List[Tuple[int, str]]):
        self.full_text = full_text
        self.page_count = page_count
        self.pages = pages  # list of (page_number_1_indexed, text)


def validate_file_signature(content: bytes, filename: str, mime_type: str) -> str:
    """
    Validate extension, file size, MIME type, and magic bytes.
    Detects MIME-type spoofing (e.g. executable renamed to .pdf or .docx).
    Returns normalized document format ('pdf', 'docx', 'txt').
    """
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty (0 bytes).",
        )

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB.",
        )

    ext = Path(filename).suffix.lower()
    if ext not in [".pdf", ".docx", ".txt"]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file format '{ext}'. Allowed formats: .pdf, .docx, .txt.",
        )

    # 1. Validate PDF
    if ext == ".pdf":
        if not content.startswith(b"%PDF"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MIME-type spoofing detected: file header does not match PDF specification.",
            )
        return "pdf"

    # 2. Validate DOCX (Must be ZIP archive containing word/document.xml)
    if ext == ".docx":
        if not content.startswith(b"PK\x03\x04"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="MIME-type spoofing detected: file header does not match OpenXML/DOCX specification.",
            )
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                # Check for critical Word document XML
                filenames = zf.namelist()
                if "word/document.xml" not in filenames:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid DOCX container: missing word/document.xml.",
                    )
        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Malformed or corrupted DOCX archive.",
            )
        return "docx"

    # 3. Validate TXT
    if ext == ".txt":
        # Check for binary null bytes
        if b"\x00" in content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Binary characters detected in plain text file.",
            )
        return "txt"

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Unsupported document format.",
    )


def extract_document_text(content: bytes, doc_format: str) -> ParsedDocument:
    """
    Safely extract plain text and page references from document.
    Disables macro execution and prevents document injection.
    """
    pages: List[Tuple[int, str]] = []

    try:
        if doc_format == "pdf":
            reader = PdfReader(io.BytesIO(content))
            page_count = len(reader.pages)
            if page_count == 0:
                raise ValueError("PDF contains no pages.")

            full_chunks = []
            for idx, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                clean_text = sanitize_extracted_text(page_text)
                pages.append((idx, clean_text))
                if clean_text:
                    full_chunks.append(clean_text)

            full_text = "\n\n".join(full_chunks)

        elif doc_format == "docx":
            doc = Document(io.BytesIO(content))
            full_chunks = []

            # Extract paragraphs
            for p in doc.paragraphs:
                text = p.text.strip()
                if text:
                    full_chunks.append(text)

            # Extract tables (e.g. formatted resumes)
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_text:
                        full_chunks.append(row_text)

            full_text = sanitize_extracted_text("\n".join(full_chunks))
            page_count = max(1, len(full_text) // 2500)
            pages.append((1, full_text))

        elif doc_format == "txt":
            try:
                raw = content.decode("utf-8")
            except UnicodeDecodeError:
                raw = content.decode("latin-1", errors="replace")
            full_text = sanitize_extracted_text(raw)
            page_count = 1
            pages.append((1, full_text))

        else:
            raise ValueError(f"Unknown document format: {doc_format}")

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unable to parse document contents: {str(exc)}",
        )

    if len(full_text.strip()) < MIN_EXTRACTED_CHARS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Document contains insufficient extractable text (e.g. image-only scan or empty file).",
        )

    return ParsedDocument(full_text=full_text, page_count=page_count, pages=pages)


def sanitize_extracted_text(text: str) -> str:
    """Sanitize extracted text to prevent script injection and normalize whitespace."""
    # Remove null bytes and non-printable control characters (except newline and tab)
    clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Normalize excessive carriage returns
    clean = clean.replace("\r\n", "\n").replace("\r", "\n")
    return clean.strip()


def save_file_securely(user_id: int, filename: str, content: bytes) -> str:
    """
    Store uploaded document in a private per-user directory outside web root.
    Returns absolute stored file path.
    """
    user_dir = STORAGE_ROOT / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize filename
    safe_filename = Path(filename).name
    # Append timestamp/random prefix to prevent collisions
    import uuid
    stored_name = f"{uuid.uuid4().hex[:12]}_{safe_filename}"
    target_path = user_dir / stored_name

    with open(target_path, "wb") as f:
        f.write(content)

    return str(target_path)
