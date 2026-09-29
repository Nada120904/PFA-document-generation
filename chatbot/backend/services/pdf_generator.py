"""PDF generation service for the document generation feature."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from services.evidence_export import evidence_from_lines, write_pdf

logger = logging.getLogger(__name__)

GENERATED_FILES_DIR = Path(__file__).resolve().parent.parent / "generated_files"
GENERATED_FILES_DIR.mkdir(parents=True, exist_ok=True)


def generate_pdf(params: dict, body_paragraphs: list[str], source_note: str) -> str:
    """Generate a PDF file from collected params and content paragraphs.

    Returns the generated filename (not the full path).
    """
    filename = f"{uuid.uuid4().hex}.pdf"
    file_path = GENERATED_FILES_DIR / filename

    title = str(params.get("title") or params.get("topic") or "Generated Document")
    write_pdf(file_path, title, evidence_from_lines(body_paragraphs))
    logger.info("pdf_generator.generated filename=%s paragraphs=%s", filename, len(body_paragraphs))
    return filename
