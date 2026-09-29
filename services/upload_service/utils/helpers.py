"""Upload service file helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

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


def build_unique_upload_path(upload_dir: str | Path, original_filename: str) -> Path:
    safe_name = Path(original_filename).name or "upload"
    suffix = detect_supported_extension(safe_name)
    if not safe_name.lower().endswith(suffix):
        safe_name = f"{safe_name}{suffix}"
    upload_path = ensure_dir(upload_dir)
    candidate = upload_path / safe_name
    if not candidate.exists():
        return candidate

    stem = Path(safe_name).stem
    extension = Path(safe_name).suffix
    counter = 1
    while True:
        candidate = upload_path / f"{stem}({counter}){extension}"
        if not candidate.exists():
            return candidate
        counter += 1


def build_unique_upload_name(original_filename: str, exists_fn: Callable[[str], bool]) -> str:
    safe_name = Path(original_filename).name or "upload"
    suffix = detect_supported_extension(safe_name)
    if not safe_name.lower().endswith(suffix):
        safe_name = f"{safe_name}{suffix}"
    if not exists_fn(safe_name):
        return safe_name

    stem = Path(safe_name).stem
    extension = Path(safe_name).suffix
    counter = 1
    while True:
        candidate = f"{stem}({counter}){extension}"
        if not exists_fn(candidate):
            return candidate
        counter += 1
