"""PDF extraction with EasyOCR only."""

from __future__ import annotations

from pathlib import Path

from services.docling_service.ingestion.easyocr_runtime import (
    build_confidence,
    get_easyocr_reader,
    render_pdf_pages,
    results_to_markdown,
    score_markdown,
    select_easyocr_language_sets,
)
from services.docling_service.logging import get_logger

logger = get_logger("rag_system.pdf.extractor")


def extract_pdf_to_markdown(file_path: str, language_hint: str = "auto") -> dict:
    """Parse a PDF with EasyOCR only, without Docling layout."""

    path = Path(file_path)
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {path.name}")

    ocr_engine = "easyocr"
    language_sets = select_easyocr_language_sets(path, language_hint=language_hint)
    best_payload: dict | None = None
    best_score: tuple[float, int] = (-1.0, -1)
    errors: list[str] = []
    pages = render_pdf_pages(file_path)

    for languages in language_sets:
        logger.info(
            "PDF OCR-only options for %s: EasyOCR without layout, languages=%s",
            path.name,
            languages,
        )
        try:
            reader = get_easyocr_reader(tuple(languages))
            all_results = []
            for page in pages:
                all_results.extend(reader.readtext(page, detail=1, paragraph=False))
        except Exception as exc:
            errors.append(f"{languages}: {exc}")
            continue

        markdown = results_to_markdown(all_results)
        if not markdown:
            errors.append(f"{languages}: empty markdown")
            continue

        scores = []
        for item in all_results:
            if len(item) >= 3:
                try:
                    scores.append(float(item[2]))
                except (TypeError, ValueError):
                    pass

        confidence = build_confidence(scores)
        current_score = score_markdown(markdown, confidence)
        payload = {
            "markdown": markdown,
            "docling_document": {
                "source": "easyocr",
                "mode": "ocr_only_no_layout",
                "file_type": "pdf",
                "languages": languages,
                "page_count": len(pages),
                "line_count": len([line for line in markdown.splitlines() if line.strip()]),
            },
            "confidence": confidence,
            "used_ocr": True,
            "ocr_engine": ocr_engine,
            "status": "processed",
            "timestamp": None,
            "easyocr_confidence": confidence.get("ocr_score") if confidence else None,
        }

        if current_score > best_score:
            best_payload = payload
            best_score = current_score

    logger.info("EasyOCR-only conversion finished for %s", path)

    if best_payload is None:
        raise ValueError(
            f"EasyOCR returned empty Markdown for PDF: {path.name}. Attempts: {' | '.join(errors)}"
        )

    return best_payload
