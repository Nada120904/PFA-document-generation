from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from services.docling_service.config import get_settings


def easyocr_languages(raw_value: str) -> list[str]:
    languages = [language.strip() for language in raw_value.split(",") if language.strip()]
    return languages or ["en"]


def select_easyocr_language_sets(path: Path, language_hint: str = "auto") -> list[list[str]]:
    settings = get_settings()
    lowered = path.as_posix().lower()
    arabic_languages = easyocr_languages(settings.easyocr_arabic_languages)
    french_languages = easyocr_languages(settings.easyocr_french_languages)
    normalized_hint = (language_hint or "auto").strip().lower()

    if normalized_hint == "arabic":
        return [arabic_languages]
    if normalized_hint == "french":
        return [french_languages]

    has_arabic_hint = any(token in lowered for token in ("_ar", "-ar", "/ar/", "arabic", "_arabic", "-arabic"))
    has_french_hint = any(token in lowered for token in ("_fr", "-fr", "/fr/", "french", "_french", "-french", "francais", "français"))

    if has_arabic_hint and has_french_hint:
        return [arabic_languages, french_languages]
    if has_arabic_hint:
        return [arabic_languages, french_languages]
    if has_french_hint:
        return [french_languages, arabic_languages]
    return [french_languages, arabic_languages]


@lru_cache(maxsize=4)
def get_easyocr_reader(languages_key: tuple[str, ...]):
    import easyocr

    settings = get_settings()
    kwargs: dict[str, Any] = {
        "lang_list": list(languages_key),
        "gpu": bool(settings.easyocr_use_gpu),
        "download_enabled": settings.easyocr_download_enabled,
    }
    if settings.easyocr_model_storage_directory:
        kwargs["model_storage_directory"] = settings.easyocr_model_storage_directory
    return easyocr.Reader(**kwargs)


def pil_image_to_array(image: Image.Image) -> np.ndarray:
    if image.mode != "RGB":
        image = image.convert("RGB")
    return np.array(image)


def render_pdf_pages(file_path: str) -> list[np.ndarray]:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(file_path)
    pages: list[np.ndarray] = []
    try:
        for index in range(len(pdf)):
            page = pdf[index]
            bitmap = page.render(scale=2.0)
            pil_image = bitmap.to_pil()
            pages.append(pil_image_to_array(pil_image))
    finally:
        pdf.close()
    return pages


def score_markdown(markdown: str, confidence: dict | None) -> tuple[float, int]:
    score = 0.0
    if confidence and confidence.get("ocr_score") is not None:
        try:
            score = float(confidence["ocr_score"])
        except (TypeError, ValueError):
            score = 0.0
    return (score, len(markdown.strip()))


def build_confidence(scores: list[float]) -> dict | None:
    if not scores:
        return None

    mean_score = sum(scores) / len(scores)
    return {
        "ocr_score": mean_score,
        "mean_score": mean_score,
        "low_score": min(scores),
        "layout_score": None,
        "parse_score": None,
        "table_score": None,
    }


def results_to_markdown(results: list[tuple[Any, str, float]]) -> str:
    lines = [text.strip() for _, text, _ in results if str(text).strip()]
    return "\n".join(lines).strip()
