"""Text processing flow built on top of Docling."""

from __future__ import annotations

from services.docling_service.ingestion.text.extractor import extract_text_to_markdown
from services.docling_service.logging import get_logger

logger = get_logger("rag_system.text.processor")


def process_text(file_path: str) -> dict:
    """Convert a text file into Markdown and return the processed result."""

    logger.info("Processing text file %s", file_path)
    extraction = extract_text_to_markdown(file_path)
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
