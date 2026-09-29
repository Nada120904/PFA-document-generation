"""DOCX processing flow built on top of Docling."""

from __future__ import annotations

from services.docling_service.ingestion.docx.extractor import extract_docx_to_markdown
from services.docling_service.logging import get_logger

logger = get_logger("rag_system.docx.processor")


def process_docx(file_path: str) -> dict:
    """Convert a DOCX into Markdown and return the processed result."""

    logger.info("Processing DOCX file %s", file_path)
    extraction = extract_docx_to_markdown(file_path)
    markdown = extraction["markdown"]

    return {
        "file_path": file_path,
        "content": markdown,
        "docling_document": extraction.get("docling_document"),
        "confidence": extraction.get("confidence"),
        "used_ocr": extraction.get("used_ocr"),
        "ocr_engine": extraction.get("ocr_engine"),
        "enrichment_summary": extraction.get("enrichment_summary"),
        "status": "processed",
    }
