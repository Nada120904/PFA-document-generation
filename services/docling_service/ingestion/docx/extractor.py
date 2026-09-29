"""DOCX extraction with Docling."""

from __future__ import annotations

import time
from pathlib import Path
from threading import Lock
from typing import Any

from services.docling_service.logging import get_logger
from services.docling_service.service import build_convert_pipeline_options

logger = get_logger("rag_system.docx.extractor")

_DOCX_CONVERTER = None
_DOCX_CONVERTER_LOCK = Lock()


def _confidence_to_dict(confidence: Any) -> dict | None:
    """Convert Docling confidence data into a serializable dict."""

    if confidence is None:
        return None

    if hasattr(confidence, "model_dump"):
        try:
            return confidence.model_dump()
        except Exception:
            pass

    if isinstance(confidence, dict):
        return confidence

    data: dict[str, Any] = {}
    for field in ("mean_grade", "low_grade", "ocr_score", "layout_score", "parse_score", "table_score"):
        if hasattr(confidence, field):
            value = getattr(confidence, field)
            if value is not None:
                data[field] = value

    return data or None


def _get_docx_converter() -> Any:
    global _DOCX_CONVERTER

    if _DOCX_CONVERTER is not None:
        return _DOCX_CONVERTER

    with _DOCX_CONVERTER_LOCK:
        if _DOCX_CONVERTER is not None:
            return _DOCX_CONVERTER

        setup_started_at = time.perf_counter()
        logger.info("Initializing cached Docling DOCX converter")
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.document_converter import DocumentConverter, WordFormatOption
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "Docling is not installed or not available in the current environment. "
                "Install it with `pip install docling`."
            ) from exc

        _DOCX_CONVERTER = DocumentConverter(
            format_options={
                InputFormat.DOCX: WordFormatOption(pipeline_options=build_convert_pipeline_options()),
            }
        )
        logger.info(
            "Cached Docling DOCX converter ready in %.3f sec",
            time.perf_counter() - setup_started_at,
        )
        return _DOCX_CONVERTER


def extract_docx_to_markdown(file_path: str) -> dict:
    """Parse a DOCX with Docling and export the result to Markdown."""

    path = Path(file_path)
    if path.suffix.lower() != ".docx":
        raise ValueError(f"Expected a DOCX file, got: {path.name}")
    converter = _get_docx_converter()
    logger.info("Starting Docling conversion for %s", path)
    result = converter.convert(path)
    markdown = result.document.export_to_markdown().strip()
    docling_document = result.document.export_to_dict()
    confidence = _confidence_to_dict(getattr(result, "confidence", None))
    logger.info("Docling conversion finished for %s", path)

    if not markdown:
        raise ValueError(f"Docling returned empty Markdown for DOCX: {path.name}")

    return {
        "markdown": markdown,
        "docling_document": docling_document,
        "confidence": confidence,
        "used_ocr": False,
        "ocr_engine": "docx-simple-pipeline",
        "status": str(getattr(result, "status", "")),
        "timestamp": getattr(result, "timestamp", None),
    }
