"""Structured context builder for the chatbot workflow."""

from __future__ import annotations

from typing import Any
from services.runtime_config import get_runtime_float

MAX_RECENT_MESSAGES = 6
MAX_MEMORY_ITEMS = 5
MAX_RETRIEVED_CHUNKS = 4
MAX_CHARS_PER_ITEM = 1200


def _clean_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= MAX_CHARS_PER_ITEM:
        return text
    return text[: MAX_CHARS_PER_ITEM - 3].rstrip() + "..."


def _normalize_recent_messages(
    recent_messages: list[dict[str, str]] | None,
) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for message in (recent_messages or [])[-MAX_RECENT_MESSAGES:]:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role", "")).strip() or "unknown"
        content = _clean_text(message.get("content", ""))
        if not content:
            continue
        normalized.append(
            {
                "role": role,
                "content": content,
            }
        )
    return normalized


def _normalize_string_items(
    items: list[str] | None,
    *,
    limit: int,
) -> list[str]:
    normalized: list[str] = []
    for item in (items or [])[:limit]:
        content = _clean_text(item)
        if content:
            normalized.append(content)
    return normalized


def _normalize_retrieved_chunks(
    chunks: list[Any] | None,
    *,
    limit: int,
) -> tuple[list[str], list[dict[str, object]]]:
    normalized_texts: list[str] = []
    normalized_records: list[dict[str, object]] = []

    for chunk in (chunks or [])[:limit]:
        if isinstance(chunk, dict):
            content = _clean_text(chunk.get("content") or chunk.get("snippet"))
            if not content:
                continue
            normalized_texts.append(content)
            normalized_records.append(
                {
                    "content": content,
                    "snippet": _clean_text(chunk.get("snippet") or content),
                    "chunk_id": chunk.get("chunk_id"),
                    "document_id": chunk.get("document_id"),
                    "file_path": chunk.get("file_path"),
                    "rerank_score": chunk.get("rerank_score"),
                    "source_query": chunk.get("source_query"),
                    "source_type": chunk.get("source_type"),
                }
            )
            continue

        content = _clean_text(chunk)
        if content:
            normalized_texts.append(content)
            normalized_records.append({"content": content})

    return normalized_texts, normalized_records


def _build_context_blocks(
    *,
    user_query: str,
    session_summary: str | None,
    recent_messages: list[dict[str, str]],
    long_term_memory: list[str],
    retrieved_chunks: list[str],
) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = [
        {
            "section": "user_query",
            "label": "Current user query",
            "items": [user_query],
        }
    ]

    if session_summary:
        blocks.append(
            {
                "section": "session_summary",
                "label": "Session summary",
                "items": [session_summary],
            }
        )

    if recent_messages:
        blocks.append(
            {
                "section": "recent_messages",
                "label": "Recent raw messages",
                "items": [f"{message['role']}: {message['content']}" for message in recent_messages],
            }
        )

    if long_term_memory:
        blocks.append(
            {
                "section": "long_term_memory",
                "label": "Long-term memory",
                "items": long_term_memory,
            }
        )

    if retrieved_chunks:
        blocks.append(
            {
                "section": "retrieved_documents",
                "label": "Retrieved document chunks",
                "items": retrieved_chunks,
            }
        )

    return blocks


def build_context(
    *,
    user_query: str,
    optimized_query: str | None = None,
    session_summary: str | None,
    recent_messages: list[dict[str, str]] | None = None,
    long_term_memory: list[str] | None = None,
    retrieved_chunks: list[Any] | None = None,
) -> dict[str, object]:
    cleaned_query = _clean_text(user_query)
    normalized_summary = _clean_text(session_summary)
    normalized_recent = _normalize_recent_messages(recent_messages)
    normalized_memory = _normalize_string_items(long_term_memory, limit=MAX_MEMORY_ITEMS)
    normalized_chunks, normalized_chunk_records = _normalize_retrieved_chunks(
        retrieved_chunks,
        limit=MAX_RETRIEVED_CHUNKS,
    )
    rerank_scores = [
        float(record["rerank_score"])
        for record in normalized_chunk_records
        if isinstance(record.get("rerank_score"), (int, float))
    ]
    min_rerank_score = get_runtime_float("CHATBOT_RETRIEVAL_MIN_RERANK_SCORE", 0.30)
    best_rerank_score = max(rerank_scores) if rerank_scores else None

    context_blocks = _build_context_blocks(
        user_query=cleaned_query,
        session_summary=normalized_summary or None,
        recent_messages=normalized_recent,
        long_term_memory=normalized_memory,
        retrieved_chunks=normalized_chunks,
    )

    return {
        "user_query": cleaned_query,
        "optimized_query": _clean_text(optimized_query) or cleaned_query,
        "session_summary": normalized_summary or None,
        "recent_messages": normalized_recent,
        "long_term_memory": normalized_memory,
        "retrieved_chunks": normalized_chunks,
        "retrieved_chunk_records": normalized_chunk_records,
        "context_blocks": context_blocks,
        "context_metadata": {
            "recent_message_count": len(normalized_recent),
            "long_term_memory_count": len(normalized_memory),
            "retrieved_chunk_count": len(normalized_chunks),
            "has_session_summary": bool(normalized_summary),
            "best_rerank_score": best_rerank_score,
            "min_rerank_score": min_rerank_score,
            "has_reliable_document_context": bool(normalized_chunks),
        },
    }
