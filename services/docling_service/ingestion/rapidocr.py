"""Shared RapidOCR model configuration for Docling OCR pipelines."""

from __future__ import annotations

from pathlib import Path

SUPPORTED_RAPIDOCR_VERSION = "PP-OCRv5"


def _normalize_version(version: str | None) -> str:
    value = (version or SUPPORTED_RAPIDOCR_VERSION).strip()
    lowered = value.lower().replace("_", "").replace("-", "")
    if lowered not in {"ppocrv5", "ppocr5", "v5"}:
        raise ValueError(
            "Only PP-OCRv5 is supported in this project. Add the PP-OCRv5 bundled files "
            "under services/docling_service/assets/rapidocr/PP-OCRv5."
        )
    return SUPPORTED_RAPIDOCR_VERSION


def _versioned_candidates(version: str) -> dict[str, tuple[Path, ...]]:
    version_dir = Path("services/docling_service/assets/rapidocr") / version
    return {
        "det_model_path": (
            version_dir / "det.onnx",
            version_dir / "ch_PP-OCRv5_det_infer.onnx",
            version_dir / "ch_PP-OCRv5_det_mobile.onnx",
        ),
        "cls_model_path": (
            version_dir / "cls.onnx",
            version_dir / "ch_ppocr_mobile_v2.0_cls_infer.onnx",
            version_dir / "ch_PP-OCRv5_cls_infer.onnx",
        ),
        "rec_model_path": (
            version_dir / "rec.onnx",
            version_dir / "ch_PP-OCRv5_rec_infer.onnx",
            version_dir / "ch_PP-OCRv5_rec_mobile.onnx",
        ),
        "rec_keys_path": (
            version_dir / "keys.txt",
            version_dir / "ppocr_keys_v1.txt",
        ),
    }


def get_bundled_rapidocr_paths(version: str | None = None) -> dict[str, str] | None:
    """Return bundled RapidOCR file paths when they are available locally."""

    normalized_version = _normalize_version(version)
    candidates = _versioned_candidates(normalized_version)
    selected: dict[str, str] = {}

    for key, paths in candidates.items():
        found = next((path for path in paths if path.exists()), None)
        if found is None:
            return None
        selected[key] = str(found)

    return selected
