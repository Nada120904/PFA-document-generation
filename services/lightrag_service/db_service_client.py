from __future__ import annotations

import asyncio
from typing import Any

import httpx

from services.lightrag_service.config import get_settings
from services.runtime_config import build_runtime_forward_headers

DB_REQUEST_RETRY_ATTEMPTS = 3
DB_REQUEST_RETRY_DELAY_SECONDS = 1.0

DB_REQUEST_RETRY_ATTEMPTS = 3
DB_REQUEST_RETRY_DELAY_SECONDS = 1.0


class DbServiceClient:
    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.db_service_base_url.rstrip("/")
        self._timeout = float(settings.db_service_timeout)
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={
                "Content-Type": "application/json",
                **build_runtime_forward_headers(),
            },
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, DB_REQUEST_RETRY_ATTEMPTS + 1):
            try:
                response = await self._client.request(method, path, json=json)
                response.raise_for_status()
                return response.json() if response.content else {}
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code < 500 or attempt == DB_REQUEST_RETRY_ATTEMPTS:
                    raise
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt == DB_REQUEST_RETRY_ATTEMPTS:
                    raise

            await asyncio.sleep(DB_REQUEST_RETRY_DELAY_SECONDS)

        if last_error is not None:
            raise last_error
        raise RuntimeError(f"DB request failed without response: method={method} path={path}")

    async def get_document(self, document_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/db/documents/{document_id}")

    async def patch_document_status(self, document_id: str, status: str) -> dict[str, Any]:
        return await self._request(
            "PATCH",
            f"/db/documents/{document_id}/status",
            json={"status": status},
        )

    async def get_latest_document_processing(self, document_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/db/document-processing/latest/{document_id}")

    async def list_indexable_document_ids(self, statuses: list[str], limit: int) -> list[dict[str, Any]]:
        payload = {"statuses": statuses, "limit": limit}
        response = await self._request("POST", "/db/document-processing/list-indexable", json=payload)
        if isinstance(response, list):
            return response
        return []

    async def create_indexing_run(self, document_id: str, pipeline_mode: str, status: str) -> str:
        payload = {"document_id": document_id, "pipeline_mode": pipeline_mode, "status": status}
        response = await self._request("POST", "/db/indexing-runs", json=payload)
        run_id = str(response.get("run_id", "")).strip()
        if not run_id:
            raise RuntimeError(f"DB service returned empty indexing run_id for document_id={document_id}.")
        return run_id

    async def patch_indexing_run(
        self,
        run_id: str,
        *,
        status: str,
        error_message: str | None = None,
        finished_at: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": status}
        if error_message is not None:
            payload["error_message"] = error_message
        if finished_at is not None:
            payload["finished_at"] = finished_at
        return await self._request("PATCH", f"/db/indexing-runs/{run_id}", json=payload)

    async def create_retrieval_run(
        self,
        *,
        query_text: str,
        mode: str,
        status: str,
        top_k: int,
        filters: dict[str, Any] | None,
        document_id: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "query_text": query_text,
            "mode": mode,
            "status": status,
            "top_k": top_k,
            "filters": filters,
            "document_id": document_id,
        }
        response = await self._request("POST", "/db/retrieval-runs", json=payload)
        run_id = str(response.get("run_id", "")).strip()
        if not run_id:
            raise RuntimeError(f"DB service returned empty retrieval run_id for query={query_text!r}.")
        return run_id

    async def patch_retrieval_run(
        self,
        run_id: str,
        *,
        document_id: str | None = None,
        status: str,
        latency_ms: int | None = None,
        error_message: str | None = None,
        response_text: str | None = None,
        score: float | None = None,
        retrieved_at: str | None = None,
        run_metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": status}
        if document_id is not None:
            payload["document_id"] = document_id
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        if error_message is not None:
            payload["error_message"] = error_message
        if response_text is not None:
            payload["response_text"] = response_text
        if score is not None:
            payload["score"] = score
        if retrieved_at is not None:
            payload["retrieved_at"] = retrieved_at
        if run_metadata is not None:
            payload["run_metadata"] = run_metadata
        return await self._request("PATCH", f"/db/retrieval-runs/{run_id}", json=payload)

    async def create_service_error(
        self,
        *,
        service_name: str,
        operation_name: str,
        status: str,
        error_message: str | None = None,
        error_context: dict[str, Any] | None = None,
        retry_count: int = 0,
        duration_ms: int | None = None,
        document_id: str | None = None,
        processing_id: str | None = None,
        indexing_run_id: str | None = None,
        retrieval_run_id: str | None = None,
        query_run_id: str | None = None,
        session_id: str | None = None,
        message_id: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "service_name": service_name,
            "operation_name": operation_name,
            "status": status,
            "error_message": error_message,
            "error_context": error_context,
            "retry_count": retry_count,
            "duration_ms": duration_ms,
            "document_id": document_id,
            "processing_id": processing_id,
            "indexing_run_id": indexing_run_id,
            "retrieval_run_id": retrieval_run_id,
            "query_run_id": query_run_id,
            "session_id": session_id,
            "message_id": message_id,
            "user_id": user_id,
        }
        return await self._request("POST", "/db/service-errors", json=payload)

    async def patch_service_error(
        self,
        error_id: str,
        *,
        status: str | None = None,
        error_message: str | None = None,
        error_context: dict[str, Any] | None = None,
        retry_count: int | None = None,
        duration_ms: int | None = None,
        resolved_at: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if status is not None:
            payload["status"] = status
        if error_message is not None:
            payload["error_message"] = error_message
        if error_context is not None:
            payload["error_context"] = error_context
        if retry_count is not None:
            payload["retry_count"] = retry_count
        if duration_ms is not None:
            payload["duration_ms"] = duration_ms
        if resolved_at is not None:
            payload["resolved_at"] = resolved_at
        return await self._request("PATCH", f"/db/service-errors/{error_id}", json=payload)

    async def map_documents_by_file_paths(self, file_paths: list[str]) -> dict[str, str]:
        payload = {"file_paths": file_paths}
        response = await self._request("POST", "/db/documents/map-by-file-paths", json=payload)
        items = response.get("items")
        if isinstance(items, dict):
            return {str(k): str(v) for k, v in items.items()}
        return {}

    async def filter_documents_by_metadata(self, filters: dict[str, list[str]], limit: int = 1000) -> list[dict[str, Any]]:
        response = await self._request(
            "POST",
            "/db/uploaded-documents/filter-by-metadata",
            json={"filters": filters, "limit": limit},
        )
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]
        return []
