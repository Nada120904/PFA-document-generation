"""Indexing text preprocessing utilities (service-local)."""

from __future__ import annotations

import re


def _canonicalize_domain_terms(text: str) -> str:
    """No domain-specific canonicalization at global preprocessing level."""
    return text


def normalize_text(text: str) -> str:
    """Clean text before indexing without using an LLM."""
    normalized = text.replace("\ufeff", "")
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.split("\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = _canonicalize_domain_terms(normalized)
    normalized = normalized.strip()

    if not normalized:
        raise ValueError("Text is empty after normalization.")

    return normalized


def summarize_section(content: str, *, max_chars: int = 900) -> str:
    cleaned = " ".join(part.strip() for part in content.splitlines() if part.strip())
    if not cleaned:
        return ""

    # Keep a deterministic short summary to avoid extra LLM cost during ingestion.
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    summary = " ".join(sentences[:4]).strip()
    if not summary:
        summary = cleaned
    if len(summary) > max_chars:
        return summary[: max_chars - 3] + "..."
    return summary


def build_document_summary_only(
    text: str,
    *,
    summary_max_chars: int = 900,
) -> str | None:
    """Build only the global document summary text for lightweight hierarchical mode."""
    global_summary = summarize_section(text, max_chars=summary_max_chars)
    if not global_summary:
        return None
    return f"[DOCUMENT SUMMARY]\n\n{global_summary}"
