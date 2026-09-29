from __future__ import annotations

from typing import Any

import httpx
from fastapi import HTTPException

from ..config import settings
from ..logging import get_logger
from services.runtime_config import build_runtime_forward_headers


logger = get_logger(__name__)


class PostgresServiceClient:
    def __init__(self) -> None:
        base_url = str(settings.POSTGRES_SERVICE_URL or "").strip()
        if not base_url:
            raise HTTPException(
                status_code=500,
                detail=(
                    "POSTGRES_SERVICE_URL is not configured. "
                    "Provide it through storage-service env vars or the "
                    "'x-rag-postgres-service-url' runtime header."
                ),
            )
        self.base_url = base_url.rstrip("/")
        self.timeout = settings.REQUEST_TIMEOUT_SECONDS

    def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        url = f"{self.base_url}{path}"

        try:
            request_headers = dict(kwargs.pop("headers", {}) or {})
            request_headers.update(build_runtime_forward_headers())

            with httpx.Client(timeout=self.timeout) as client:
                response = client.request(method, url, headers=request_headers, **kwargs)

            if response.status_code >= 400:
                logger.error(
                    "Postgres service error: method=%s url=%s status=%s body=%s",
                    method,
                    url,
                    response.status_code,
                    response.text,
                )
                raise HTTPException(
                    status_code=502,
                    detail={
                        "message": "Postgres service returned an error",
                        "status_code": response.status_code,
                        "response": response.text,
                    },
                )

            if not response.content:
                return None

            return response.json()

        except HTTPException:
            raise

        except httpx.RequestError as exc:
            logger.error("Could not reach postgres_service: %s", exc)
            raise HTTPException(
                status_code=502,
                detail=f"Could not reach postgres_service: {exc}",
            ) from exc

    def create_document(
        self,
        *,
        document_id: str,
        storage_backend: str,
        file_name: str,
        file_path: str,
        mime_type: str | None = None,
        doc_type: str | None = None,
        file_hash: str | None = None,
        metadata_json: dict[str, str] | None = None,
        status: str = "stored",
    ) -> dict[str, Any]:
        payload = {
            "document_id": document_id,
            "storage_backend": storage_backend,
            "file_name": file_name,
            "file_path": file_path,
            "mime_type": mime_type,
            "doc_type": doc_type,
            "file_hash": file_hash,
            "metadata_json": metadata_json,
            "status": status,
        }

        return self._request(
            "POST",
            "/db/uploaded-documents",
            json=payload,
        )

    def get_document(self, document_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/db/uploaded-documents/{document_id}",
        )

    def update_document(
        self,
        document_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "PATCH",
            f"/db/uploaded-documents/{document_id}",
            json=payload,
        )

    def list_storage_documents(
        self,
        *,
        storage_backend: str,
        file_path_prefix: str | None = None,
        exclude_status: str | None = "deleted",
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "storage_backend": storage_backend,
            "exclude_status": exclude_status,
            "limit": limit,
        }

        if file_path_prefix:
            params["file_path_prefix"] = file_path_prefix

        return self._request(
            "GET",
            "/db/storage/documents",
            params=params,
        )
