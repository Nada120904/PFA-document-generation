"""Retrieval API routes (clean service + RAGAS only evaluation)."""

from __future__ import annotations

import datetime
import hashlib
import logging
import re
import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.lightrag_service.config import get_settings
from services.lightrag_service.db_service_client import DbServiceClient
from services.lightrag_service.lightrag_client import (
    call_rerank,
    use_lightrag_retrieval_allowed_documents,
)
from services.lightrag_service.retrieval.workflow import run_text_retrieval

router = APIRouter(prefix="/retrieval", tags=["retrieval"])
logger = logging.getLogger(__name__)

_QUERY_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "from",
    "into",
    "what",
    "which",
    "how",
    "are",
    "is",
    "in",
    "of",
    "to",
    "on",
    "a",
    "an",
    "by",
    "as",
}
_MIN_CHUNK_RANK_SCORE = 1.0


class RetrievalRequest(BaseModel):
    query: str = Field(..., description="User query text to retrieve relevant content")
    top_k: int = Field(5, ge=1, le=50, description="Number of results to return")
    search_type: str = Field("hybrid", description="LightRAG search type (naive, local, global, hybrid, mix)")
    answer: str | None = Field(default=None, description="Optional generated answer for answer-level RAGAS metrics.")
    reference: str | None = Field(default=None, description="Optional reference used by RAGAS context/answer metrics.")
    max_entities: int = Field(5, ge=0, le=20, description="Max entities to include in preview output")
    max_relations: int = Field(5, ge=0, le=20, description="Max relationships to include in preview output")
    max_chunks: int = Field(3, ge=0, le=20, description="Max chunks to include in preview output")
    max_chunk_chars: int = Field(400, ge=50, le=4000, description="Max chars per chunk preview")
    enable_reranker: bool = Field(True, description="Enable query-aware reranking of retrieved chunks")
    rerank_top_n: int = Field(20, ge=1, le=200, description="Number of candidate chunks to rerank")
    generate_answer: bool = Field(True, description="Generate final answer using retrieved chunks")
    evaluate_ragas: bool = Field(True, description="Run RAGAS evaluation before returning response")
    answer_style: str = Field(
        "clear_structured",
        description="Answer style hint for generation (clear_structured, concise, detailed)",
    )
    generation_max_chunks: int = Field(5, ge=1, le=20, description="Max chunks to pass to answer generation")
    generation_max_chunk_chars: int = Field(
        1200, ge=100, le=6000, description="Max chars per chunk passed to generation"
    )
    insufficient_context_threshold: float = Field(
        0.25,
        ge=0.0,
        le=1.0,
        description="Minimum context relevance score required to consider context sufficient.",
    )
    filters: dict[str, list[str]] | None = Field(
        default=None,
        description="Optional document metadata filters applied before returning retrieval results.",
    )


def _normalize_filters(filters: dict[str, list[str]] | None) -> dict[str, list[str]] | None:
    if not isinstance(filters, dict):
        return None
    normalized: dict[str, list[str]] = {}
    for key, values in filters.items():
        key_text = str(key).strip()
        if not key_text or not isinstance(values, list):
            continue
        normalized_values = [str(value).strip() for value in values if str(value).strip()]
        if normalized_values:
            normalized[key_text] = normalized_values
    return normalized or None


def _tokenize_query(query: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Z0-9_]+", query.lower())
    return {t for t in tokens if len(t) >= 3 and t not in _QUERY_STOPWORDS}


def _chunk_signature(content: str) -> str:
    normalized = re.sub(r"\s+", " ", content.strip().lower())
    return hashlib.sha1(normalized[:1200].encode("utf-8")).hexdigest()


def _chunk_rank_score(chunk: dict[str, Any], query_terms: set[str]) -> float:
    content = chunk.get("content")
    if not isinstance(content, str) or not content.strip():
        return -1.0

    lowered = content.lower()
    token_hits = sum(1 for term in query_terms if term in lowered)
    starts_section = lowered.startswith("[section]")
    starts_section_summary = lowered.startswith("[section summary]")
    starts_document_summary = lowered.startswith("[document summary]")
    has_intro = "introduction" in lowered
    line_count = max(content.count("\n") + 1, 1)
    pipe_count = content.count("|")
    digit_count = sum(1 for c in content if c.isdigit())
    table_like_ratio = pipe_count / float(line_count)
    digit_ratio = digit_count / float(max(len(content), 1))

    score = float(token_hits) * 10.0
    if starts_section:
        score += 3.0
    if starts_section_summary:
        score += 2.0
    if starts_document_summary:
        score += 1.0
    if has_intro and token_hits <= 1:
        score -= 4.0
    if table_like_ratio > 0.35 and digit_ratio > 0.08:
        score -= 8.0
    elif table_like_ratio > 0.25:
        score -= 4.0
    return score


def _postprocess_retrieval_data(
    retrieval_data: dict[str, Any] | None,
    *,
    query: str,
    enable_reranker: bool = True,
    rerank_top_n: int = 20,
) -> tuple[dict[str, Any] | None, dict[str, int]]:
    if not isinstance(retrieval_data, dict):
        return retrieval_data, {
            "chunks_before": 0,
            "chunks_after": 0,
            "duplicates_removed": 0,
            "low_score_removed": 0,
            "reranker_enabled": int(enable_reranker),
            "reranked_candidates": 0,
        }

    data = retrieval_data.get("data")
    if not isinstance(data, dict):
        return retrieval_data, {
            "chunks_before": 0,
            "chunks_after": 0,
            "duplicates_removed": 0,
            "low_score_removed": 0,
            "reranker_enabled": int(enable_reranker),
            "reranked_candidates": 0,
        }

    chunks = data.get("chunks")
    if not isinstance(chunks, list):
        return retrieval_data, {
            "chunks_before": 0,
            "chunks_after": 0,
            "duplicates_removed": 0,
            "low_score_removed": 0,
            "reranker_enabled": int(enable_reranker),
            "reranked_candidates": 0,
        }

    query_terms = _tokenize_query(query)
    has_native_rerank_scores = any(
        isinstance(chunk, dict) and isinstance(chunk.get("rerank_score"), (int, float))
        for chunk in chunks
    )
    scored: list[tuple[float, dict[str, Any]]] = []
    for chunk in chunks:
        if isinstance(chunk, dict):
            if has_native_rerank_scores:
                scored.append((float(chunk.get("rerank_score", 0.0)), chunk))
            else:
                scored.append((_chunk_rank_score(chunk, query_terms), chunk))

    if enable_reranker:
        scored = scored[:rerank_top_n]
        scored.sort(key=lambda item: item[0], reverse=True)
    else:
        scored = [(0.0, chunk) for chunk in chunks if isinstance(chunk, dict)]

    filtered_chunks: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    low_score_removed = 0

    for score, chunk in scored:
        content = chunk.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if (
            enable_reranker
            and not has_native_rerank_scores
            and score < _MIN_CHUNK_RANK_SCORE
        ):
            low_score_removed += 1
            continue

        signature = _chunk_signature(content)
        if signature in seen_signatures:
            continue

        seen_signatures.add(signature)
        filtered_chunks.append(chunk)

    references = data.get("references", [])
    reference_by_path: dict[str, dict[str, Any]] = {}
    if isinstance(references, list):
        for ref in references:
            if isinstance(ref, dict):
                ref_path = ref.get("file_path")
                if isinstance(ref_path, str):
                    reference_by_path[ref_path] = ref

    filtered_paths: list[str] = []
    for chunk in filtered_chunks:
        file_path = chunk.get("file_path")
        if isinstance(file_path, str) and file_path not in filtered_paths:
            filtered_paths.append(file_path)

    filtered_references: list[dict[str, Any]] = []
    for idx, path in enumerate(filtered_paths, start=1):
        existing = reference_by_path.get(path)
        if existing is not None:
            filtered_references.append(existing)
        else:
            filtered_references.append({"reference_id": str(idx), "file_path": path})

    data["chunks"] = filtered_chunks
    data["references"] = filtered_references

    chunks_before = len(chunks)
    chunks_after = len(filtered_chunks)
    return retrieval_data, {
        "chunks_before": chunks_before,
        "chunks_after": chunks_after,
        "duplicates_removed": max(chunks_before - chunks_after, 0),
        "low_score_removed": low_score_removed,
        "reranker_enabled": int(enable_reranker),
        "native_rerank_scores": int(has_native_rerank_scores),
        "reranked_candidates": min(len(chunks), rerank_top_n) if enable_reranker else 0,
    }


def _extract_contexts(retrieval_data: dict[str, Any] | None) -> list[str]:
    if not retrieval_data:
        return []
    data = retrieval_data.get("data", {}) if isinstance(retrieval_data, dict) else {}
    chunks = data.get("chunks", []) if isinstance(data, dict) else []
    contexts: list[str] = []
    for chunk in chunks:
        if isinstance(chunk, dict):
            content = chunk.get("content")
            if isinstance(content, str) and content.strip():
                contexts.append(content)
    return contexts


def _extract_document_ids_from_preview(preview: dict[str, Any]) -> list[str]:
    document_ids: set[str] = set()
    for key in ("top_chunks", "references"):
        items = preview.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            document_id = item.get("document_id")
            if isinstance(document_id, str) and document_id.strip():
                document_ids.add(document_id)
    return sorted(document_ids)


def _extract_best_rerank_score(retrieval_data: dict[str, Any] | None) -> float | None:
    if not isinstance(retrieval_data, dict):
        return None
    data = retrieval_data.get("data")
    if not isinstance(data, dict):
        return None
    chunks = data.get("chunks")
    if not isinstance(chunks, list):
        return None
    scores = [
        float(chunk["rerank_score"])
        for chunk in chunks
        if isinstance(chunk, dict) and isinstance(chunk.get("rerank_score"), (int, float))
    ]
    if not scores:
        return None
    return max(scores)


def _has_rerank_scores(retrieval_data: dict[str, Any] | None) -> bool:
    if not isinstance(retrieval_data, dict):
        return False
    data = retrieval_data.get("data")
    if not isinstance(data, dict):
        return False
    chunks = data.get("chunks")
    if not isinstance(chunks, list):
        return False
    return any(
        isinstance(chunk, dict) and isinstance(chunk.get("rerank_score"), (int, float))
        for chunk in chunks
    )


async def _apply_manual_rerank_scores_if_needed(
    retrieval_data: dict[str, Any] | None,
    *,
    query: str,
    enabled: bool,
    top_n: int,
) -> tuple[dict[str, Any] | None, bool]:
    if not enabled or not isinstance(retrieval_data, dict) or _has_rerank_scores(retrieval_data):
        return retrieval_data, False

    settings = get_settings()
    if settings.rerank_binding.strip().lower() not in {"huggingface", "hf", "local"}:
        return retrieval_data, False

    data = retrieval_data.get("data")
    if not isinstance(data, dict):
        return retrieval_data, False
    chunks = data.get("chunks")
    if not isinstance(chunks, list) or not chunks:
        return retrieval_data, False

    documents: list[str] = []
    chunk_indexes: list[int] = []
    for idx, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            continue
        content = chunk.get("content")
        if isinstance(content, str) and content.strip():
            chunk_indexes.append(idx)
            documents.append(content)

    if not documents:
        return retrieval_data, False

    try:
        rerank_results = await call_rerank(
            query=query,
            documents=documents,
            top_n=min(top_n, len(documents)),
            settings=settings,
        )
    except Exception as exc:
        logger.warning("retrieval.step step=manual_rerank skipped=true error=%s", exc)
        return retrieval_data, False

    scored_chunks: list[dict[str, Any]] = []
    seen_indexes: set[int] = set()
    for result in rerank_results:
        if not isinstance(result, dict):
            continue
        result_index = result.get("index")
        relevance_score = result.get("relevance_score")
        if not isinstance(result_index, int) or not isinstance(relevance_score, (int, float)):
            continue
        if result_index < 0 or result_index >= len(chunk_indexes):
            continue
        original_index = chunk_indexes[result_index]
        original_chunk = chunks[original_index]
        if not isinstance(original_chunk, dict):
            continue
        updated_chunk = original_chunk.copy()
        updated_chunk["rerank_score"] = float(relevance_score)
        scored_chunks.append(updated_chunk)
        seen_indexes.add(original_index)

    if not scored_chunks:
        return retrieval_data, False

    min_score = float(settings.min_rerank_score or 0.0)
    if min_score > 0:
        scored_chunks = [
            chunk for chunk in scored_chunks if float(chunk.get("rerank_score", 0.0)) >= min_score
        ]
    if not scored_chunks:
        data["chunks"] = []
    else:
        data["chunks"] = scored_chunks

    logger.info(
        "retrieval.step step=manual_rerank applied=true binding=%s chunks_before=%s chunks_after=%s top_n=%s",
        settings.rerank_binding,
        len(documents),
        len(data["chunks"]),
        top_n,
    )
    return retrieval_data, True


def _trim_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3] + "..."


def _build_preview(
    retrieval_data: dict[str, Any] | None,
    *,
    max_entities: int,
    max_relations: int,
    max_chunks: int,
    max_chunk_chars: int,
    document_id_by_path: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not retrieval_data:
        return {"top_entities": [], "top_relations": [], "top_chunks": [], "references": []}

    data = retrieval_data.get("data", {}) if isinstance(retrieval_data, dict) else {}
    entities = data.get("entities", []) if isinstance(data, dict) else []
    relationships = data.get("relationships", []) if isinstance(data, dict) else []
    chunks = data.get("chunks", []) if isinstance(data, dict) else []
    references = data.get("references", []) if isinstance(data, dict) else []

    top_entities = []
    for entity in entities[:max_entities]:
        if isinstance(entity, dict):
            top_entities.append(
                {
                    "entity_name": entity.get("entity_name"),
                    "entity_type": entity.get("entity_type"),
                }
            )

    top_relations = []
    for relation in relationships[:max_relations]:
        if isinstance(relation, dict):
            top_relations.append(
                {
                    "src_id": relation.get("src_id"),
                    "tgt_id": relation.get("tgt_id"),
                    "weight": relation.get("weight"),
                }
            )

    top_chunks = []
    for chunk in chunks[:max_chunks]:
        if not isinstance(chunk, dict):
            continue
        content = chunk.get("content")
        snippet = _trim_text(content, max_chunk_chars) if isinstance(content, str) else None
        chunk_file_path = chunk.get("file_path")
        chunk_document_id = (
            document_id_by_path.get(chunk_file_path)
            if isinstance(chunk_file_path, str) and isinstance(document_id_by_path, dict)
            else None
        )
        top_chunks.append(
            {
                "chunk_id": chunk.get("chunk_id"),
                "file_path": chunk_file_path,
                "document_id": chunk_document_id,
                "rerank_score": chunk.get("rerank_score"),
                "content": content,
                "snippet": snippet,
            }
        )

    slim_references = []
    for ref in references[: max(max_chunks, 1)]:
        if isinstance(ref, dict):
            ref_file_path = ref.get("file_path")
            ref_document_id = (
                document_id_by_path.get(ref_file_path)
                if isinstance(ref_file_path, str) and isinstance(document_id_by_path, dict)
                else None
            )
            slim_references.append(
                {
                    "reference_id": ref.get("reference_id"),
                    "file_path": ref_file_path,
                    "document_id": ref_document_id,
                }
            )

    return {
        "top_entities": top_entities,
        "top_relations": top_relations,
        "top_chunks": top_chunks,
        "references": slim_references,
    }


def _filter_retrieval_data_by_file_paths(
    retrieval_data: dict[str, Any] | None,
    *,
    allowed_file_paths: set[str],
) -> dict[str, Any] | None:
    if not isinstance(retrieval_data, dict):
        return retrieval_data

    data = retrieval_data.get("data")
    if not isinstance(data, dict):
        return retrieval_data

    chunks = data.get("chunks")
    if isinstance(chunks, list):
        data["chunks"] = [
            chunk
            for chunk in chunks
            if isinstance(chunk, dict)
            and isinstance(chunk.get("file_path"), str)
            and chunk.get("file_path") in allowed_file_paths
        ]

    references = data.get("references")
    if isinstance(references, list):
        data["references"] = [
            ref
            for ref in references
            if isinstance(ref, dict)
            and isinstance(ref.get("file_path"), str)
            and ref.get("file_path") in allowed_file_paths
        ]

    return retrieval_data


async def _build_document_id_map(
    retrieval_data: dict[str, Any] | None,
    db_client: DbServiceClient,
) -> dict[str, str]:
    if not isinstance(retrieval_data, dict):
        return {}

    data = retrieval_data.get("data", {})
    if not isinstance(data, dict):
        return {}

    paths: set[str] = set()
    chunks = data.get("chunks", [])
    references = data.get("references", [])

    if isinstance(chunks, list):
        for chunk in chunks:
            if isinstance(chunk, dict):
                file_path = chunk.get("file_path")
                if isinstance(file_path, str) and file_path.strip():
                    paths.add(file_path)

    if isinstance(references, list):
        for ref in references:
            if isinstance(ref, dict):
                file_path = ref.get("file_path")
                if isinstance(file_path, str) and file_path.strip():
                    paths.add(file_path)

    if not paths:
        return {}

    return await db_client.map_documents_by_file_paths(list(paths))


@router.post("/text")
async def retrieve_text(body: RetrievalRequest) -> dict:
    normalized_filters = _normalize_filters(body.filters)
    logger.info(
        "retrieval.start query=%r mode=%s top_k=%s reranker=%s filters=%s",
        body.query,
        body.search_type,
        body.top_k,
        body.enable_reranker,
        normalized_filters,
    )
    db_client = DbServiceClient()
    retrieval_run_id: str | None = None
    try:
        try:
            retrieval_run_id = await db_client.create_retrieval_run(
                query_text=body.query,
                mode="text",
                status="running",
                top_k=body.top_k,
                filters=normalized_filters,
                document_id=None,
            )
        except Exception as exc:
            retrieval_run_id = None
            logger.warning("retrieval.step step=create_retrieval_run skipped=true error=%s", exc)

        allowed_file_paths: set[str] | None = None
        allowed_document_ids: set[str] | None = None
        if normalized_filters:
            filter_start = time.perf_counter()
            filtered_documents = await db_client.filter_documents_by_metadata(normalized_filters)
            allowed_document_ids = {
                str(document.get("document_id")).strip()
                for document in filtered_documents
                if isinstance(document.get("document_id"), str) and str(document.get("document_id")).strip()
            }
            allowed_file_paths = {
                str(document.get("file_path")).strip()
                for document in filtered_documents
                if isinstance(document.get("file_path"), str) and str(document.get("file_path")).strip()
            }
            logger.info(
                "retrieval.step step=resolve_metadata_filters elapsed_ms=%s matches=%s",
                int((time.perf_counter() - filter_start) * 1000),
                len(allowed_file_paths),
            )
            if not allowed_file_paths:
                empty_preview = {"top_entities": [], "top_relations": [], "top_chunks": [], "references": []}
                if retrieval_run_id:
                    try:
                        await db_client.patch_retrieval_run(
                            run_id=retrieval_run_id,
                            status="ok",
                            latency_ms=0,
                            response_text=None,
                            score=None,
                            retrieved_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                            run_metadata={
                                "search_type": body.search_type,
                                "top_k": body.top_k,
                                "filters": normalized_filters,
                                "retrieved_chunks_count": 0,
                                "insufficient_context": True,
                                "insufficient_context_reason": "no_documents_match_filters",
                                "clarification_needed": False,
                                "clarification_reason": None,
                                "best_rerank_score": None,
                                "clarification_threshold": body.insufficient_context_threshold,
                                "document_ids": [],
                                "retrieval_preview": empty_preview,
                                "generation_error": None,
                                "ragas": {
                                    "available": False,
                                    "reason": "disabled_in_service",
                                    "scores": {},
                                    "errors": {},
                                },
                            },
                        )
                    except Exception as patch_exc:
                        logger.warning("retrieval.step step=patch_retrieval_run_empty skipped=true error=%s", patch_exc)
                return {
                    "retrieval_id": retrieval_run_id,
                    "latency_ms": 0,
                    "query": body.query,
                    "top_k": body.top_k,
                    "search_type": body.search_type,
                    "generated_answer": None,
                    "citations": [],
                    "generation_error": None,
                    "retrieval_preview": empty_preview,
                    "evaluation": {
                        "retrieved_chunks_count": 0,
                        "insufficient_context": True,
                        "insufficient_context_reason": "no_documents_match_filters",
                        "clarification_needed": False,
                        "clarification_reason": None,
                        "best_rerank_score": None,
                        "clarification_threshold": body.insufficient_context_threshold,
                        "ragas": {
                            "available": False,
                            "reason": "disabled_in_service",
                            "scores": {},
                            "errors": {},
                        },
                    },
                }

        start = time.perf_counter()
        try:
            retrieval_core_start = time.perf_counter()
            with use_lightrag_retrieval_allowed_documents(
                document_ids=sorted(allowed_document_ids or []),
                file_paths=sorted(allowed_file_paths or []),
            ):
                result = await run_text_retrieval(
                    query=body.query,
                    top_k=body.top_k,
                    search_type=body.search_type,
                    enable_rerank=body.enable_reranker,
                )
            logger.info(
                "retrieval.step step=run_text_retrieval elapsed_ms=%s mode=%s top_k=%s",
                int((time.perf_counter() - retrieval_core_start) * 1000),
                body.search_type,
                body.top_k,
            )
        except Exception as exc:  # pragma: no cover
            if retrieval_run_id:
                try:
                    await db_client.patch_retrieval_run(
                        run_id=retrieval_run_id,
                        status="error",
                        error_message=str(exc),
                    )
                except Exception as patch_exc:
                    logger.warning("retrieval.step step=patch_retrieval_run_error skipped=true error=%s", patch_exc)
            logger.exception(
                "retrieval.error query=%r mode=%s top_k=%s",
                body.query,
                body.search_type,
                body.top_k,
            )
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        duration_ms = int((time.perf_counter() - start) * 1000)

        retrieval_data = result.get("retrieval_data")
        if allowed_file_paths is not None:
            retrieval_data = _filter_retrieval_data_by_file_paths(
                retrieval_data if isinstance(retrieval_data, dict) else None,
                allowed_file_paths=allowed_file_paths,
            )
        manual_rerank_applied = False
        retrieval_data, manual_rerank_applied = await _apply_manual_rerank_scores_if_needed(
            retrieval_data if isinstance(retrieval_data, dict) else None,
            query=body.query,
            enabled=body.enable_reranker,
            top_n=body.rerank_top_n,
        )
        postprocess_start = time.perf_counter()
        retrieval_data, _dedup_stats = _postprocess_retrieval_data(
            retrieval_data if isinstance(retrieval_data, dict) else None,
            query=body.query,
            enable_reranker=body.enable_reranker,
            rerank_top_n=body.rerank_top_n,
        )
        logger.info(
            (
                "retrieval.step step=postprocess_chunks elapsed_ms=%s chunks_before=%s "
                "chunks_after=%s duplicates_removed=%s low_score_removed=%s "
                "native_rerank_scores=%s reranked_candidates=%s"
            ),
            int((time.perf_counter() - postprocess_start) * 1000),
            _dedup_stats.get("chunks_before"),
            _dedup_stats.get("chunks_after"),
            _dedup_stats.get("duplicates_removed"),
            _dedup_stats.get("low_score_removed"),
            _dedup_stats.get("native_rerank_scores"),
            _dedup_stats.get("reranked_candidates"),
        )

        context_start = time.perf_counter()
        contexts = _extract_contexts(retrieval_data if isinstance(retrieval_data, dict) else None)
        logger.info(
            "retrieval.step step=extract_contexts elapsed_ms=%s chunks=%s",
            int((time.perf_counter() - context_start) * 1000),
            len(contexts),
        )

        doc_map_start = time.perf_counter()
        document_id_by_path = await _build_document_id_map(
            retrieval_data if isinstance(retrieval_data, dict) else None,
            db_client,
        )
        logger.info(
            "retrieval.step step=build_document_id_map elapsed_ms=%s paths=%s",
            int((time.perf_counter() - doc_map_start) * 1000),
            len(document_id_by_path),
        )

        preview_start = time.perf_counter()
        preview = _build_preview(
            retrieval_data if isinstance(retrieval_data, dict) else None,
            max_entities=body.max_entities,
            max_relations=body.max_relations,
            max_chunks=body.max_chunks,
            max_chunk_chars=body.max_chunk_chars,
            document_id_by_path=document_id_by_path,
        )
        logger.info(
            "retrieval.step step=build_preview elapsed_ms=%s",
            int((time.perf_counter() - preview_start) * 1000),
        )

        generated_answer: str | None = None
        answer_citations: list[dict[str, Any]] = []
        generation_error: str | None = None
        ragas_eval = {
            "available": False,
            "reason": "disabled_in_service",
            "scores": {},
            "errors": {},
        }
        logger.info("retrieval.step step=generate_answer skipped=true reason=disabled_in_service")
        logger.info("retrieval.step step=ragas_evaluate skipped=true reason=disabled_in_service")

        insufficient_context = len(contexts) == 0
        insufficient_context_reason: str | None = (
            "no_chunks_retrieved" if insufficient_context else None
        )
        best_rerank_score = _extract_best_rerank_score(
            retrieval_data if isinstance(retrieval_data, dict) else None
        )
        clarification_needed = (
            not insufficient_context
            and best_rerank_score is not None
            and best_rerank_score < body.insufficient_context_threshold
        )
        clarification_reason: str | None = (
            "low_rerank_score" if clarification_needed else None
        )
        preview_document_ids = _extract_document_ids_from_preview(preview)
        resolved_document_id = preview_document_ids[0] if len(preview_document_ids) == 1 else None
        retrieved_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        run_metadata = {
            "search_type": result.get("search_type", body.search_type),
            "top_k": result.get("top_k", body.top_k),
            "filters": normalized_filters,
            "enable_reranker": body.enable_reranker,
            "rerank_top_n": body.rerank_top_n,
            "manual_rerank_applied": manual_rerank_applied,
            "dedup_stats": _dedup_stats,
            "retrieved_chunks_count": len(contexts),
            "insufficient_context": insufficient_context,
            "insufficient_context_reason": insufficient_context_reason,
            "clarification_needed": clarification_needed,
            "clarification_reason": clarification_reason,
            "best_rerank_score": best_rerank_score,
            "clarification_threshold": body.insufficient_context_threshold,
            "document_ids": preview_document_ids,
            "retrieval_preview": preview,
            "generation_error": generation_error,
            "ragas": ragas_eval,
            "score_definition": "best_rerank_score"
            if best_rerank_score is not None
            else "not_available_from_lightrag_response",
            "top_chunks_ranking": "rerank_score_then_deduplicate"
            if best_rerank_score is not None
            else (
                "local_query_term_rerank_then_deduplicate"
                if body.enable_reranker
                else "lightrag_response_order_then_deduplicate"
            ),
        }

        if retrieval_run_id:
            try:
                await db_client.patch_retrieval_run(
                    run_id=retrieval_run_id,
                    document_id=resolved_document_id,
                    status="ok",
                    latency_ms=duration_ms,
                    response_text=generated_answer,
                    score=best_rerank_score,
                    retrieved_at=retrieved_at,
                    run_metadata=run_metadata,
                )
            except Exception as patch_exc:
                logger.warning("retrieval.step step=patch_retrieval_run_ok skipped=true error=%s", patch_exc)

        logger.info(
            (
                "retrieval.done retrieval_id=%s mode=%s top_k=%s latency_ms=%s "
                "chunks=%s insufficient_context=%s clarification_needed=%s best_rerank_score=%s"
            ),
            retrieval_run_id,
            result.get("search_type", body.search_type),
            result.get("top_k", body.top_k),
            duration_ms,
            len(contexts),
            insufficient_context,
            clarification_needed,
            best_rerank_score,
        )

        return {
            "retrieval_id": retrieval_run_id,
            "latency_ms": duration_ms,
            "query": result.get("query", body.query),
            "top_k": result.get("top_k", body.top_k),
            "search_type": result.get("search_type", body.search_type),
            "generated_answer": generated_answer,
            "citations": answer_citations,
            "generation_error": generation_error,
            "retrieval_preview": preview,
            "evaluation": {
                "retrieved_chunks_count": len(contexts),
                "insufficient_context": insufficient_context,
                "insufficient_context_reason": insufficient_context_reason,
                "clarification_needed": clarification_needed,
                "clarification_reason": clarification_reason,
                "best_rerank_score": best_rerank_score,
                "clarification_threshold": body.insufficient_context_threshold,
                "ragas": ragas_eval,
            },
        }
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"DB service error: {exc}") from exc
    finally:
        await db_client.aclose()
