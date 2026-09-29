"""Image extraction with EasyOCR only."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from services.docling_service.ingestion.easyocr_runtime import (
    build_confidence,
    get_easyocr_reader,
    pil_image_to_array,
    results_to_markdown,
    score_markdown,
    select_easyocr_language_sets,
)
from services.docling_service.logging import get_logger

logger = get_logger("rag_system.image.ocr")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


def extract_image_to_markdown(file_path: str, language_hint: str = "auto") -> dict:
    """Parse an image with EasyOCR only, without Docling layout."""

    path = Path(file_path)
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        raise ValueError(f"Expected an image file, got: {path.name}")

    ocr_engine = "easyocr"
    language_sets = select_easyocr_language_sets(path, language_hint=language_hint)
    best_payload: dict | None = None
    best_score: tuple[float, int] = (-1.0, -1)
    errors: list[str] = []
    image_array = pil_image_to_array(Image.open(path))

    for languages in language_sets:
        logger.info(
            "Image OCR-only options for %s: EasyOCR without layout, languages=%s",
            path.name,
            languages,
        )
        try:
            reader = get_easyocr_reader(tuple(languages))
            results = reader.readtext(image_array, detail=1, paragraph=False)
        except Exception as exc:
            errors.append(f"{languages}: {exc}")
            continue

        markdown = results_to_markdown(results)
        if not markdown:
            errors.append(f"{languages}: empty markdown")
            continue

        scores = []
        for item in results:
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
                "file_type": "image",
                "languages": languages,
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
            f"EasyOCR returned empty Markdown for image: {path.name}. Attempts: {' | '.join(errors)}"
        )

    return best_payload
