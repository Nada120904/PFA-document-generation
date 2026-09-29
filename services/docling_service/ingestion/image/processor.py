"""Image processing flow built on top of Docling."""

from __future__ import annotations

from services.docling_service.ingestion.image.ocr import extract_image_to_markdown
from services.docling_service.logging import get_logger

logger = get_logger("rag_system.image.processor")


def process_image(file_path: str, language_hint: str = "auto") -> dict:
    """Convert an image into Markdown and return the processed result."""

    logger.info("Processing image file %s", file_path)
    extraction = extract_image_to_markdown(file_path, language_hint=language_hint)
    markdown = extraction["markdown"]

    return {
        "file_path": file_path,
        "content": markdown,
        "docling_document": extraction.get("docling_document"),
        "confidence": extraction.get("confidence"),
        "used_ocr": extraction.get("used_ocr"),
        "easyocr_confidence": extraction.get("easyocr_confidence"),
        "ocr_engine": extraction.get("ocr_engine"),
        "enrichment_summary": extraction.get("enrichment_summary"),
        "status": "processed",
    }
