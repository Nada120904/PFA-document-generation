"""Text indexing workflow (service-local)."""

from __future__ import annotations

from contextlib import contextmanager
import logging
import time
from pathlib import Path
from typing import Any

from services.lightrag_service.indexing.hierarchical_processing import (
    build_document_summary_only,
    normalize_text,
)
from services.lightrag_service.indexing.entity_postprocess import dedupe_entities_for_file
from services.lightrag_service.config import get_settings
from services.lightrag_service.lightrag_client import (
    activate_lightrag_runtime_env,
    get_lightrag_client,
    sync_document_metadata_to_neo4j,
    use_lightrag_document_metadata,
)

logger = logging.getLogger(__name__)
_SUCCESS_DOC_STATUSES = {"processed", "preprocessed"}


def _coerce_status(value: Any) -> str:
    if value is None:
        return ""
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        return enum_value.lower()
    return str(value).lower()


async def _assert_doc_processed(client: Any, *, doc_id: str, step: str) -> None:
    doc_status_store = getattr(client, "doc_status", None)
    if doc_status_store is None or not hasattr(doc_status_store, "get_by_id"):
        return

    status_row = await doc_status_store.get_by_id(doc_id)
    if not isinstance(status_row, dict):
        raise RuntimeError(
            f"LightRAG did not persist document status for document_id={doc_id} (step={step})."
        )

    status = _coerce_status(status_row.get("status"))
    if status in _SUCCESS_DOC_STATUSES:
        return

    error_msg = status_row.get("error_msg") or status_row.get("error") or "unknown"
    raise RuntimeError(
        f"LightRAG extraction failed/incomplete for document_id={doc_id} "
        f"(step={step}, status={status or 'missing'}, error={error_msg})."
    )


def read_text_file(file_path: str) -> str:
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    if not path.is_file():
        raise ValueError(f"Path is not a file: {file_path}")
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")


def run_text_indexing(file_path: str) -> dict:
    content = normalize_text(read_text_file(file_path))
    return {"file_path": file_path, "content": content, "status": "extracted"}


def _filter_docs_for_ids(docs: Any, allowed_ids: set[str]) -> Any:
    if isinstance(docs, dict):
        filtered_dict: dict[Any, Any] = {}
        for key, value in docs.items():
            key_str = str(key)

            # Common case: status -> nested docs map/list
            if isinstance(value, (dict, list)):
                nested = _filter_docs_for_ids(value, allowed_ids)
                if nested:
                    filtered_dict[key] = nested
                continue

            # Fallback: direct doc object/value
            obj_id = None
            if hasattr(value, "doc_id"):
                obj_id = getattr(value, "doc_id")
            elif hasattr(value, "id"):
                obj_id = getattr(value, "id")

            if key_str in allowed_ids or (obj_id is not None and str(obj_id) in allowed_ids):
                filtered_dict[key] = value

        return filtered_dict
    if isinstance(docs, list):
        filtered = []
        for item in docs:
            if isinstance(item, dict):
                track_id = item.get("id") or item.get("track_id") or item.get("doc_id")
                if track_id is not None and str(track_id) in allowed_ids:
                    filtered.append(item)
            elif hasattr(item, "id"):
                track_id = getattr(item, "id")
                if track_id is not None and str(track_id) in allowed_ids:
                    filtered.append(item)
            elif hasattr(item, "doc_id"):
                doc_id = getattr(item, "doc_id")
                if doc_id is not None and str(doc_id) in allowed_ids:
                    filtered.append(item)
        return filtered
    return docs


@contextmanager
def _restrict_pipeline_to_ids(client: Any, allowed_ids: set[str]):
    """
    LightRAG ainsert() processes global pending/failed docs from its local state.
    For API by-document mode, restrict that selection to the current request track IDs.
    """
    doc_status = getattr(client, "doc_status", None)
    if doc_status is None or not hasattr(doc_status, "get_docs_by_status"):
        yield
        return

    original_get_docs_by_status = doc_status.get_docs_by_status

    async def _patched_get_docs_by_status(*args, **kwargs):  # type: ignore[no-untyped-def]
        docs = await original_get_docs_by_status(*args, **kwargs)
        return _filter_docs_for_ids(docs, allowed_ids)

    doc_status.get_docs_by_status = _patched_get_docs_by_status  # type: ignore[method-assign]
    try:
        yield
    finally:
        doc_status.get_docs_by_status = original_get_docs_by_status  # type: ignore[method-assign]


async def run_text_lightrag_indexing(
    *,
    file_path: str,
    document_id: str,
    content: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict:
    """End-to-end indexing using LightRAG (chunks + vectors + graph)."""

    total_start = time.perf_counter()
    settings = get_settings()
    allowed_doc_ids: set[str] = {document_id}
    async with activate_lightrag_runtime_env():
        client = get_lightrag_client()
        init_start = time.perf_counter()
        await client.initialize_storages()
        logger.info(
            "indexing.step document_id=%s step=initialize_storages elapsed_ms=%s",
            document_id,
            int((time.perf_counter() - init_start) * 1000),
        )

        final_content = content if content is not None else read_text_file(file_path)
        normalize_start = time.perf_counter()
        final_content = normalize_text(final_content)
        logger.info(
            "indexing.step document_id=%s step=normalize_content elapsed_ms=%s",
            document_id,
            int((time.perf_counter() - normalize_start) * 1000),
        )

        insert_main_start = time.perf_counter()
        with use_lightrag_document_metadata(
            document_id=document_id,
            file_path=file_path,
            metadata=metadata,
        ):
            with _restrict_pipeline_to_ids(client, allowed_doc_ids):
                track_id = await client.ainsert(input=final_content, ids=document_id, file_paths=file_path)
        await _assert_doc_processed(client, doc_id=document_id, step="insert_main")
        logger.info(
            "indexing.step document_id=%s step=insert_main elapsed_ms=%s",
            document_id,
            int((time.perf_counter() - insert_main_start) * 1000),
        )

        additional_track_ids: list[str] = []
        section_count = 0
        section_summary_count = 0
        has_document_summary = False

        if settings.lightrag_enable_hierarchical_ingestion:
            hierarchy_build_start = time.perf_counter()
            document_summary = build_document_summary_only(
                final_content,
                summary_max_chars=settings.lightrag_hierarchical_summary_max_chars,
            )
            logger.info(
                "indexing.step document_id=%s step=build_document_summary_only elapsed_ms=%s sections=%s summaries=%s has_doc_summary=%s",
                document_id,
                int((time.perf_counter() - hierarchy_build_start) * 1000),
                0,
                0,
                bool(document_summary),
            )

            if document_summary:
                insert_doc_summary_start = time.perf_counter()
                level_id = f"{document_id}:sumdoc"
                allowed_doc_ids.add(level_id)
                with use_lightrag_document_metadata(
                    document_id=document_id,
                    file_path=file_path,
                    metadata=metadata,
                ):
                    with _restrict_pipeline_to_ids(client, allowed_doc_ids):
                        level_track_id = await client.ainsert(input=document_summary, ids=level_id, file_paths=file_path)
                await _assert_doc_processed(client, doc_id=level_id, step="insert_document_summary")
                additional_track_ids.append(level_track_id)
                has_document_summary = True
                logger.info(
                    "indexing.step document_id=%s step=insert_document_summary elapsed_ms=%s",
                    document_id,
                    int((time.perf_counter() - insert_doc_summary_start) * 1000),
                )

        if metadata:
            sync_start = time.perf_counter()
            await sync_document_metadata_to_neo4j(
                client=client,
                document_id=document_id,
                file_path=file_path,
                metadata=metadata,
            )
            logger.info(
                "indexing.step document_id=%s step=sync_document_metadata_to_neo4j elapsed_ms=%s",
                document_id,
                int((time.perf_counter() - sync_start) * 1000),
            )

    dedup_result: dict | None = None
    if settings.lightrag_enable_entity_dedup_postprocess:
        dedup_start = time.perf_counter()
        dedup_result = dedupe_entities_for_file(file_path=file_path)
        logger.info(
            "indexing.step document_id=%s step=entity_dedup elapsed_ms=%s deleted_rows=%s duplicate_groups=%s",
            document_id,
            int((time.perf_counter() - dedup_start) * 1000),
            dedup_result.get("deleted_rows") if isinstance(dedup_result, dict) else None,
            dedup_result.get("duplicate_groups") if isinstance(dedup_result, dict) else None,
        )

    logger.info(
        "indexing.step document_id=%s step=workflow_total elapsed_ms=%s",
        document_id,
        int((time.perf_counter() - total_start) * 1000),
    )

    return {
        "file_path": file_path,
        "status": "indexed",
        "track_id": track_id,
        "additional_track_ids": additional_track_ids,
        "hierarchical_ingestion": {
            "enabled": settings.lightrag_enable_hierarchical_ingestion,
            "sections_indexed": section_count,
            "section_summaries_indexed": section_summary_count,
            "document_summary_indexed": has_document_summary,
        },
        "post_processing": {
            "entity_dedup": dedup_result,
        },
    }
