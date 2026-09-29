"""API and UI routes for the orchestration service."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse

from services.orchestration_service.models import (
    OrchestrationDocumentDeleteRequest,
    DoclingTriggerRequest,
    OrchestrationRetrievalRequest,
    PipelineResponse,
    ServiceStatusResponse,
)
from services.runtime_config import extract_runtime_overrides, use_runtime_overrides
from services.runtime_config import build_runtime_forward_headers
from services.orchestration_service.service import (
    choose_confidence,
    delete_storage_file,
    get_document_by_id,
    fetch_service_status,
    get_document_by_path,
    get_uploaded_document_metadata_options,
    get_latest_indexing_run,
    purge_uploaded_document,
    get_latest_processing,
    init_tables,
    list_documents,
    run_lightrag_indexing,
    run_lightrag_delete,
    run_lightrag_retrieval,
    run_docling,
    should_use_vlm,
    trigger_vlm,
    upload_base64_file,
    upload_file,
    upload_file_with_metadata,
    wait_for_vlm,
)
from services.upload_service.utils.helpers import detect_supported_extension

router = APIRouter(tags=["orchestration"])

STATIC_DIR = Path(__file__).resolve().parent / "static"


def _build_indexing_result(*, uploaded_document: dict, document_id: str | None, latest_indexing: dict | None) -> dict | None:
    if latest_indexing:
        return {
            "status": latest_indexing.get("status"),
            "document_id": latest_indexing.get("document_id") or document_id,
            "run_id": latest_indexing.get("indexing_run_id"),
            "pipeline_mode": latest_indexing.get("pipeline_mode"),
            "error_message": latest_indexing.get("error_message"),
            "indexed_at": latest_indexing.get("indexed_at"),
            "finished_at": latest_indexing.get("finished_at"),
            "updated_at": latest_indexing.get("updated_at"),
            "run_metadata": latest_indexing.get("run_metadata"),
        }

    document_status = str(uploaded_document.get("status") or "").strip().lower()
    if document_status != "indexed":
        return None

    return {
        "status": "indexed",
        "document_id": document_id,
    }


@router.get("/")
def read_ui() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@router.get("/orchestration/status", response_model=ServiceStatusResponse)
async def read_status(request: Request) -> ServiceStatusResponse:
    with use_runtime_overrides(extract_runtime_overrides(request.headers)):
        return ServiceStatusResponse(**(await fetch_service_status()))


@router.post("/orchestration/postgres/init")
async def create_tables(request: Request) -> dict:
    try:
        with use_runtime_overrides(extract_runtime_overrides(request.headers)):
            return await init_tables()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or "Postgres init failed."
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Postgres service: {exc}") from exc


@router.post("/orchestration/upload")
async def upload_document(
    request: Request,
    provider: str = Query(default="nextcloud"),
    file: UploadFile | None = File(default=None),
) -> dict:
    try:
        with use_runtime_overrides(extract_runtime_overrides(request.headers)):
            content_type = request.headers.get("content-type", "").lower()
            if content_type.startswith("application/json"):
                payload = await request.json()
                if not isinstance(payload, dict):
                    raise HTTPException(status_code=400, detail="Invalid JSON upload payload.")
                return await upload_base64_file(payload, provider=provider)

            if file is None:
                raise HTTPException(
                    status_code=400,
                    detail="Multipart upload requires a file field named 'file'.",
                )
            extension = detect_supported_extension(file.filename or "")
            if extension in {".pdf", ".docx"}:
                raise HTTPException(
                    status_code=400,
                    detail="PDF and DOCX uploads must use the Base64 JSON upload flow.",
                )
            content = await file.read()
            form = await request.form()
            parsed_metadata: dict[str, str] | None = None
            raw_metadata = form.get("metadata_json")
            if isinstance(raw_metadata, str) and raw_metadata.strip():
                try:
                    parsed = json.loads(raw_metadata)
                except json.JSONDecodeError as exc:
                    raise HTTPException(status_code=400, detail="metadata_json must be valid JSON.") from exc
                if not isinstance(parsed, dict):
                    raise HTTPException(status_code=400, detail="metadata_json must be a JSON object.")
                parsed_metadata = {
                    str(key).strip(): str(value).strip()
                    for key, value in parsed.items()
                    if str(key).strip() and str(value).strip()
                }
            return await upload_file_with_metadata(
                file.filename or "upload.bin",
                content,
                file.content_type,
                provider=provider,
                metadata_json=parsed_metadata,
            )
    except HTTPException:
        raise
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or "Upload failed."
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Upload service: {exc}") from exc


@router.get("/orchestration/document-state")
async def read_document_state(request: Request, file_path: str = Query(...)) -> dict:
    try:
        with use_runtime_overrides(extract_runtime_overrides(request.headers)):
            uploaded_document = await get_document_by_path(file_path)
            document_id = uploaded_document.get("document_id")
            latest_processing = None
            latest_indexing = None
            if isinstance(document_id, str) and document_id.strip():
                try:
                    latest_processing = await get_latest_processing(document_id)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 404:
                        raise
                try:
                    latest_indexing = await get_latest_indexing_run(document_id)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 404:
                        raise

            indexing_result = _build_indexing_result(
                uploaded_document=uploaded_document,
                document_id=document_id if isinstance(document_id, str) else None,
                latest_indexing=latest_indexing,
            )

            return {
                "uploaded_document": uploaded_document,
                "latest_processing": latest_processing,
                "indexing_result": indexing_result,
            }
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or "Could not read document state."
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach downstream service: {exc}") from exc


@router.get("/orchestration/document-state/by-document-id")
async def read_document_state_by_document_id(request: Request, document_id: str = Query(...)) -> dict:
    try:
        with use_runtime_overrides(extract_runtime_overrides(request.headers)):
            uploaded_document = await get_document_by_id(document_id)
            latest_processing = None
            latest_indexing = None
            if isinstance(document_id, str) and document_id.strip():
                try:
                    latest_processing = await get_latest_processing(document_id)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 404:
                        raise
                try:
                    latest_indexing = await get_latest_indexing_run(document_id)
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 404:
                        raise

            indexing_result = _build_indexing_result(
                uploaded_document=uploaded_document,
                document_id=document_id if isinstance(document_id, str) else None,
                latest_indexing=latest_indexing,
            )

            return {
                "uploaded_document": uploaded_document,
                "latest_processing": latest_processing,
                "indexing_result": indexing_result,
            }
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or "Could not read document state."
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach downstream service: {exc}") from exc


@router.get("/orchestration/document-metadata/options")
async def read_document_metadata_options(request: Request) -> dict:
    try:
        with use_runtime_overrides(extract_runtime_overrides(request.headers)):
            return await get_uploaded_document_metadata_options()
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or "Could not read metadata options."
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Postgres service: {exc}") from exc


@router.get("/orchestration/documents")
async def read_documents(limit: int | None = Query(default=None)) -> list[dict]:
    try:
        return await list_documents(limit=limit)
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or "Document listing failed."
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach Postgres service: {exc}") from exc


@router.post("/orchestration/process", response_model=PipelineResponse)
async def process_document(request: Request, payload: DoclingTriggerRequest) -> PipelineResponse:
    try:
        with use_runtime_overrides(extract_runtime_overrides(request.headers)):
            runtime_headers = build_runtime_forward_headers()
            uploaded_document = await get_document_by_path(payload.file_path)
            docling_result = await run_docling(payload.file_path, payload.language_hint)
            latest_processing = await get_latest_processing(uploaded_document["document_id"])
            confidence_source, confidence_value = choose_confidence(
                latest_processing=latest_processing,
                docling_result=docling_result,
            )

            final_markdown = docling_result.get("markdown_text") or latest_processing.get("markdown_text")
            final_message = "Docling result kept."
            vlm_triggered = False
            vlm_result = None

            if should_use_vlm(document=uploaded_document, confidence=confidence_value):
                vlm_triggered = True
                await trigger_vlm(docling_result["processing_id"], headers=runtime_headers)
                vlm_result = await wait_for_vlm(docling_result["processing_id"], headers=runtime_headers)
                latest_processing = await get_latest_processing(uploaded_document["document_id"])
                final_markdown = latest_processing.get("markdown_text")
                final_message = "VLM fallback was triggered because OCR confidence was below the threshold."
            else:
                final_message = "Docling confidence was high enough, so VLM was not triggered."

            return PipelineResponse(
                uploaded_document=uploaded_document,
                docling_result=docling_result,
                latest_processing=latest_processing,
                confidence_source=confidence_source,
                confidence_value=confidence_value,
                vlm_triggered=vlm_triggered,
                vlm_result=vlm_result,
                final_markdown=final_markdown,
                final_message=final_message,
            )
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or "Orchestration request failed."
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Service communication failed: {exc}") from exc


@router.post("/orchestration/lightrag/index-by-path")
async def index_document_in_lightrag(request: Request, payload: DoclingTriggerRequest) -> dict:
    try:
        with use_runtime_overrides(extract_runtime_overrides(request.headers)):
            uploaded_document = await get_document_by_path(payload.file_path)
            document_id = uploaded_document.get("document_id")
            if not isinstance(document_id, str) or not document_id.strip():
                raise HTTPException(status_code=400, detail="document_id not found for provided file_path")

            result = await run_lightrag_indexing(document_id=document_id)
            return {
                "file_path": payload.file_path,
                "document_id": document_id,
                "indexing_result": result,
            }
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or "LightRAG indexing failed."
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach LightRAG service: {exc}") from exc


@router.post("/orchestration/document/delete")
async def delete_one_document_everywhere(payload: OrchestrationDocumentDeleteRequest) -> dict:
    try:
        if payload.document_id:
            uploaded_document = await get_document_by_id(payload.document_id)
        elif payload.file_path:
            uploaded_document = await get_document_by_path(payload.file_path)
        else:
            raise HTTPException(status_code=400, detail="Provide document_id or file_path.")

        document_id = uploaded_document.get("document_id")
        if not isinstance(document_id, str) or not document_id.strip():
            raise HTTPException(status_code=400, detail="document_id not found.")

        results: dict[str, object] = {
            "document_id": document_id,
            "file_path": uploaded_document.get("file_path"),
            "storage_delete_result": None,
            "lightrag_delete_result": None,
            "postgres_purge_result": None,
        }
        errors: list[dict[str, str]] = []

        if payload.delete_storage_file:
            try:
                results["storage_delete_result"] = await delete_storage_file(document_id)
            except Exception as exc:
                errors.append({"step": "storage", "error": str(exc)})

        if payload.delete_lightrag:
            try:
                results["lightrag_delete_result"] = await run_lightrag_delete(
                    document_id=document_id,
                    delete_llm_cache=payload.delete_llm_cache,
                )
            except Exception as exc:
                errors.append({"step": "lightrag", "error": str(exc)})

        if payload.delete_project_postgres:
            try:
                results["postgres_purge_result"] = await purge_uploaded_document(document_id=document_id)
            except Exception as exc:
                errors.append({"step": "postgres", "error": str(exc)})

        return {
            "status": "deleted" if not errors else "deleted_with_errors",
            **results,
            "errors": errors,
            "chatbot_visibility": (
                "removed_from_retrieval_when_lightrag_and_postgres_delete_succeed"
                if payload.delete_lightrag and payload.delete_project_postgres and not any(
                    error["step"] in {"lightrag", "postgres"} for error in errors
                )
                else "may_remain_visible_if_lightrag_or_postgres_delete_was_disabled_or_failed"
            ),
        }
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or "Document delete failed."
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach downstream service: {exc}") from exc


@router.post("/orchestration/lightrag/retrieve")
async def retrieve_with_lightrag(payload: OrchestrationRetrievalRequest) -> dict:
    try:
        return await run_lightrag_retrieval(
            query=payload.query,
            top_k=payload.top_k,
            search_type=payload.search_type,
            generate_answer=payload.generate_answer,
            evaluate_ragas=payload.evaluate_ragas,
            answer=payload.answer,
            reference=payload.reference,
            filters=payload.filters,
        )
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text or "LightRAG retrieval failed."
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach LightRAG service: {exc}") from exc
