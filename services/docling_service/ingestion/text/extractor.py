"""Plain-text extraction helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.docling_service.logging import get_logger
from services.docling_service.service import build_convert_pipeline_options

logger = get_logger("rag_system.text.extractor")


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


def read_text_file(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as file:
        content = file.read().strip()

    if not content:
        raise ValueError(f"Text file is empty after stripping whitespace: {file_path}")

    return content


def extract_text_to_markdown(file_path: str) -> dict:
    """Read a `.txt` file and pass its content through Docling as Markdown."""

    path = Path(file_path)
    if path.suffix.lower() != ".txt":
        raise ValueError(f"Expected a TXT file, got: {path.name}")

    content = read_text_file(file_path)

    try:
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import DocumentConverter, MarkdownFormatOption
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "Docling is not installed or not available in the current environment. "
            "Install it with `pip install docling`."
        ) from exc

    converter = DocumentConverter(
        format_options={
            InputFormat.MD: MarkdownFormatOption(pipeline_options=build_convert_pipeline_options()),
        }
    )
    logger.info("Starting Docling conversion for %s", path)
    result = converter.convert_string(content=content, format=InputFormat.MD, name=path.with_suffix(".md").name)
    markdown = result.document.export_to_markdown().strip()
    docling_document = result.document.export_to_dict()
    confidence = _confidence_to_dict(getattr(result, "confidence", None))

    if not markdown:
        raise ValueError(f"Docling returned empty Markdown for TXT: {path.name}")

    return {
        "markdown": markdown,
        "docling_document": docling_document,
        "confidence": confidence,
        "used_ocr": False,
        "ocr_engine": "docling-md-string",
        "status": str(getattr(result, "status", "")),
        "timestamp": getattr(result, "timestamp", None),
    }
