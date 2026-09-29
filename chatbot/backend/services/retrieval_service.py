"""RAG retrieval service for the chatbot workflow."""

from __future__ import annotations

import logging
from typing import Any

from chatbot.backend.services.service_clients import lightrag_post
from services.runtime_config import get_runtime_bool, get_runtime_env, get_runtime_float, get_runtime_int

logger = logging.getLogger(__name__)


def retrieve_document_context(
    query: str,
    *,
    original_query: str | None = None,
    variants: list[str] | None = None,
    sub_questions: list[str] | None = None,
    filters: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    if not get_runtime_bool("CHATBOT_RETRIEVAL_ENABLED", False):
        return []

    optimized_text = query.strip()
    original_text = (original_query or optimized_text).strip()
    if not original_text and not optimized_text:
        return []

    merged_chunks: list[dict[str, Any]] = []
    retrieval_queries: list[str] = []
    original_chunks: list[dict[str, Any]] = []

    if original_text:
        retrieval_queries.append(original_text)
        original_chunks = _retrieve_single_query_with_filters(
            original_text,
            source_type="original",
            filters=filters,
        )
        merged_chunks.extend(original_chunks)

    original_best_score = _best_rerank_score(original_chunks)
    original_sufficient_threshold = get_runtime_float(
        "CHATBOT_RETRIEVAL_ORIGINAL_SUFFICIENT_SCORE",
        0.60,
    )
    original_is_sufficient = (
        original_best_score is not None
        and original_best_score >= original_sufficient_threshold
    )

    optimized_queries: list[str] = []
    if not original_is_sufficient:
        optimized_queries = _build_optimized_retrieval_queries(
            optimized_text,
            variants=variants,
            sub_questions=sub_questions,
            exclude={original_text},
        )

    for retrieval_query in optimized_queries:
        retrieval_queries.append(retrieval_query)
        merged_chunks.extend(
            _retrieve_single_query_with_filters(
                retrieval_query,
                source_type="optimized",
                filters=filters,
            )
        )

    deduped = _dedupe_chunk_records(merged_chunks)
    if deduped:
        logger.info(
            (
                "documents.retrieve original_query=%r optimized_query=%r "
                "original_best_score=%s original_sufficient=%s filters=%r retrieval_queries=%r hits=%s top_scores=%r"
            ),
            original_text,
            optimized_text,
            original_best_score,
            original_is_sufficient,
            filters,
            retrieval_queries,
            len(deduped),
            [chunk.get("rerank_score") for chunk in deduped[:5]],
        )
    else:
        logger.info(
            (
                "documents.retrieve original_query=%r optimized_query=%r "
                "original_best_score=%s original_sufficient=%s filters=%r retrieval_queries=%r hits=0 snippets=[]"
            ),
            original_text,
            optimized_text,
            original_best_score,
            original_is_sufficient,
            filters,
            retrieval_queries,
        )
    return deduped


def _retrieve_single_query_with_filters(
    query: str,
    *,
    source_type: str,
    filters: dict[str, list[str]] | None,
) -> list[dict[str, Any]]:
    search_type = str(get_runtime_env("CHATBOT_RETRIEVAL_SEARCH_TYPE", "hybrid")).strip() or "hybrid"
    top_k = max(1, get_runtime_int("CHATBOT_RETRIEVAL_TOP_K", 4))
    max_chunks = max(1, get_runtime_int("CHATBOT_RETRIEVAL_MAX_CHUNKS", top_k))
    max_chunk_chars = max(200, get_runtime_int("CHATBOT_RETRIEVAL_MAX_CHUNK_CHARS", 4000))
    rerank_top_n = max(1, get_runtime_int("CHATBOT_RETRIEVAL_RERANK_TOP_N", 20))
    enable_reranker = get_runtime_bool("CHATBOT_RETRIEVAL_ENABLE_RERANKER", True)
    status_code, payload = lightrag_post(
        "/retrieval/text",
        {
            "query": query,
            "search_type": search_type,
            "top_k": top_k,
            "max_chunks": max_chunks,
            "max_chunk_chars": max_chunk_chars,
            "enable_reranker": enable_reranker,
            "rerank_top_n": rerank_top_n,
            "filters": filters,
            "generate_answer": False,
            "evaluate_ragas": False,
        },
    )
    if status_code >= 400:
        raise RuntimeError(
            f"Document retrieval failed through LightRAG with status {status_code}: {payload!r}"
        )
    if not isinstance(payload, dict):
        raise RuntimeError("Document retrieval returned an invalid LightRAG response.")

    preview = payload.get("retrieval_preview", {})
    if not isinstance(preview, dict):
        raise RuntimeError("Document retrieval response is missing retrieval_preview.")

    chunks = preview.get("top_chunks", [])
    if not isinstance(chunks, list):
        raise RuntimeError("Document retrieval response is missing top_chunks.")

    normalized: list[dict[str, Any]] = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        content = str(chunk.get("content") or chunk.get("snippet") or "").strip()
        if not content:
            continue
        normalized.append(
            {
                "content": content,
                "snippet": str(chunk.get("snippet") or content).strip(),
                "chunk_id": chunk.get("chunk_id"),
                "document_id": chunk.get("document_id"),
                "file_path": chunk.get("file_path"),
                "rerank_score": chunk.get("rerank_score"),
                "source_query": query,
                "source_type": source_type,
            }
        )
    return normalized


def _build_optimized_retrieval_queries(
    query: str,
    *,
    variants: list[str] | None,
    sub_questions: list[str] | None,
    exclude: set[str] | None = None,
) -> list[str]:
    candidates = []
    if sub_questions:
        candidates.extend(sub_questions)
    elif variants:
        candidates.extend(variants)
    elif query:
        candidates.append(query)
    excluded = {item.strip() for item in (exclude or set()) if item.strip()}
    return _dedupe_chunks(
        [item.strip() for item in candidates if item.strip() and item.strip() not in excluded]
    )[:5]


def _dedupe_chunks(chunks: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for chunk in chunks:
        key = " ".join(chunk.lower().split())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)
    return deduped


def _dedupe_chunk_records(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    min_score = get_runtime_float("CHATBOT_RETRIEVAL_MIN_RERANK_SCORE", 0.30)
    has_rerank_scores = any(
        isinstance(chunk.get("rerank_score"), (int, float)) for chunk in chunks
    )
    total_chunks = len(chunks)
    duplicate_removed = 0
    low_score_removed = 0
    missing_score_removed = 0

    def sort_key(chunk: dict[str, Any]) -> float:
        score = chunk.get("rerank_score")
        return float(score) if isinstance(score, (int, float)) else -1.0

    for chunk in sorted(chunks, key=sort_key, reverse=True):
        score = chunk.get("rerank_score")
        if has_rerank_scores and not isinstance(score, (int, float)):
            missing_score_removed += 1
            continue
        if has_rerank_scores and float(score) < min_score:
            low_score_removed += 1
            continue
        content = str(chunk.get("content") or "").strip()
        chunk_id = str(chunk.get("chunk_id") or "").strip()
        key = chunk_id or " ".join(content.lower().split())
        if not key or key in seen:
            duplicate_removed += 1
            continue
        seen.add(key)
        deduped.append(chunk)

    context_top_n = max(1, get_runtime_int("CHATBOT_RETRIEVAL_CONTEXT_TOP_N", 4))
    final_chunks = deduped[:context_top_n]
    logger.info(
        (
            "documents.filter total=%s final=%s has_rerank_scores=%s "
            "missing_score_removed=%s low_score_removed=%s duplicate_removed=%s top_n=%s min_rerank_score=%s"
        ),
        total_chunks,
        len(final_chunks),
        has_rerank_scores,
        missing_score_removed,
        low_score_removed,
        duplicate_removed,
        context_top_n,
        min_score,
    )
    if has_rerank_scores and not deduped:
        logger.info(
            "documents.retrieve filtered_all_chunks=true min_rerank_score=%s",
            min_score,
        )
    return final_chunks


def _best_rerank_score(chunks: list[dict[str, Any]]) -> float | None:
    scores = [
        float(chunk["rerank_score"])
        for chunk in chunks
        if isinstance(chunk.get("rerank_score"), (int, float))
    ]
    return max(scores) if scores else None
