"""Docling service file helpers."""

from __future__ import annotations

from pathlib import Path

SUPPORTED_UPLOAD_EXTENSIONS = {
    ".txt",
    ".pdf",
    ".docx",
    ".jpg",
    ".jpeg",
    ".png",
    ".tif",
    ".tiff",
    ".bmp",
    ".webp",
}


def ensure_dir(path: str | Path) -> Path:
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def detect_supported_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_UPLOAD_EXTENSIONS:
        raise ValueError(
            "Unsupported file type "
            f"'{suffix or '<none>'}'. Supported types: .txt, .pdf, .docx, .jpg, .jpeg, .png, .tif, .tiff, .bmp, .webp"
        )
    return suffix


def build_artifact_base_name(source_file_name: str) -> str:
    source_name = Path(source_file_name).name or "document"
    return Path(source_name).stem
