"""Indexing API routes (DB-driven, no upload)."""

from __future__ import annotations

import datetime
import logging
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.lightrag_service.db_service_client import DbServiceClient
from services.lightrag_service.indexing.workflow import run_text_lightrag_indexing
from services.lightrag_service.lightrag_client import activate_lightrag_runtime_env, get_lightrag_client

router = APIRouter(prefix="/indexing", tags=["indexing"])
logger = logging.getLogger(__name__)


def _infer_doc_type(file_path: str) -> str:
    suffix = Path(file_path).suffix.lower().lstrip(".")
    return suffix or "unknown"


class IndexDocumentRequest(BaseModel):
    document_id: str = Field(..., description="Existing uploaded_documents.document_id")


class IndexBatchRequest(BaseModel):
    document_ids: list[str] | None = Field(
        default=None,
        description="Optional list of document IDs. If omitted, takes pending parsed documents.",
    )
    limit: int = Field(10, ge=1, le=200, description="Max docs processed when document_ids not provided")


class DeleteDocumentRequest(BaseModel):
    document_id: str = Field(..., description="Existing uploaded_documents.document_id")
    delete_llm_cache: bool = Field(
        default=False,
        description="Also delete LLM cache entries tied to this document.",
    )


def _result_to_dict(result: object) -> dict:
    if hasattr(result, "model_dump"):
        return getattr(result, "model_dump")()
    if hasattr(result, "dict"):
        return getattr(result, "dict")()
    if isinstance(result, dict):
        return result
    return {
        "status": str(getattr(result, "status", "unknown")),
        "doc_id": str(getattr(result, "doc_id", "")),
        "message": str(getattr(result, "message", "")),
        "status_code": int(getattr(result, "status_code", 200)),
        "file_path": getattr(result, "file_path", None),
    }


async def _index_one_document(db_client: DbServiceClient, document_id: str) -> dict:
    t0 = time.perf_counter()
    logger.info("indexing.start document_id=%s", document_id)
    try:
        document = await db_client.get_document(document_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            logger.error("indexing.error document_not_found document_id=%s", document_id)
            raise HTTPException(status_code=404, detail=f"Document not found: {document_id}") from exc
        raise HTTPException(status_code=502, detail=f"DB service error: {exc}") from exc

    try:
        processing = await db_client.get_latest_document_processing(document_id)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            logger.error("indexing.error no_processing_row document_id=%s", document_id)
            raise HTTPException(
                status_code=400,
                detail=f"No document_processing row found for document_id={document_id}.",
            ) from exc
        raise HTTPException(status_code=502, detail=f"DB service error: {exc}") from exc

    try:
        final_content = processing.get("markdown_text")
        if not isinstance(final_content, str) or not final_content.strip():
            raise ValueError("No markdown_text available in document_processing row.")
    except Exception as exc:
        logger.exception("indexing.error markdown_load_failed document_id=%s", document_id)
        raise HTTPException(
            status_code=400,
            detail=f"Unable to load markdown for document_id={document_id}: {exc}",
        ) from exc

    await db_client.patch_document_status(document_id=document_id, status="running")
    run_id = await db_client.create_indexing_run(document_id=document_id, pipeline_mode="text-full-db", status="running")
    file_path = str(document.get("file_path", ""))
    if not file_path:
        raise HTTPException(status_code=400, detail=f"Empty file_path for document_id={document_id}")
    metadata = document.get("metadata_json")
    if not isinstance(metadata, dict):
        metadata = None

    try:
        result = await run_text_lightrag_indexing(
            file_path=file_path,
            document_id=document_id,
            content=final_content,
            metadata=metadata,
        )
    except Exception as exc:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        await db_client.patch_document_status(document_id=document_id, status="error")
        await db_client.patch_indexing_run(
            run_id=run_id,
            status="error",
            error_message=str(exc),
            finished_at=now,
        )
        logger.exception("indexing.error document_id=%s", document_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    await db_client.patch_document_status(document_id=document_id, status=result["status"])
    await db_client.patch_indexing_run(
        run_id=run_id,
        status=result["status"],
        finished_at=now,
    )
    latency_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "indexing.done document_id=%s run_id=%s status=%s latency_ms=%s",
        document_id,
        run_id,
        result["status"],
        latency_ms,
    )

    return {
        "document_id": document_id,
        "run_id": run_id,
        "file_path": file_path,
        **result,
    }


@router.post("/text/full/by-document")
async def index_text_full_by_document(body: IndexDocumentRequest) -> dict:
    db_client = DbServiceClient()
    try:
        return await _index_one_document(db_client, body.document_id)
    finally:
        await db_client.aclose()


@router.post("/text/full/batch-from-db")
async def index_text_full_batch_from_db(body: IndexBatchRequest) -> dict:
    db_client = DbServiceClient()
    target_ids: list[str]
    try:
        if body.document_ids:
            target_ids = body.document_ids
        else:
            rows = await db_client.list_indexable_document_ids(
                statuses=["parsed", "completed", "ready"],
                limit=body.limit,
            )
            target_ids = [str(row.get("document_id")) for row in rows if isinstance(row, dict) and row.get("document_id")]

        if not target_ids:
            return {"status": "no_documents", "processed": 0, "results": [], "errors": []}

        results: list[dict] = []
        errors: list[dict] = []
        for doc_id in target_ids:
            try:
                item = await _index_one_document(db_client, doc_id)
                results.append(item)
            except HTTPException as exc:
                errors.append({"document_id": doc_id, "error": exc.detail})
            except Exception as exc:  # pragma: no cover
                errors.append({"document_id": doc_id, "error": str(exc)})

        return {
            "status": "ok" if not errors else "partial",
            "processed": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
        }
    finally:
        await db_client.aclose()


@router.post("/text/full/delete/by-document")
async def delete_text_full_by_document(body: DeleteDocumentRequest) -> dict:
    t0 = time.perf_counter()
    logger.info("delete.start document_id=%s", body.document_id)
    async with activate_lightrag_runtime_env():
        client = get_lightrag_client()
        await client.initialize_storages()
        raw = await client.adelete_by_doc_id(
            doc_id=body.document_id,
            delete_llm_cache=body.delete_llm_cache,
        )
    payload = _result_to_dict(raw)
    latency_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        "delete.done document_id=%s status=%s latency_ms=%s",
        body.document_id,
        payload.get("status"),
        latency_ms,
    )
    return {
        "document_id": body.document_id,
        "delete_llm_cache": body.delete_llm_cache,
        "latency_ms": latency_ms,
        "result": payload,
    }
