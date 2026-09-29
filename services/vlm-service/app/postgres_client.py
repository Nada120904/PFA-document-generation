from __future__ import annotations

from typing import Any

import requests

from app.config import get_settings
from app.logging import get_logger
from app.runtime_config import build_runtime_forward_headers


logger = get_logger(__name__)


class PostgresServiceError(RuntimeError):
    pass


class PostgresClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.postgres_service_url.rstrip("/")
        self.timeout = settings.request_timeout_seconds

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_payload: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = self._url(path)

        try:
            response = requests.request(
                method=method,
                url=url,
                json=json_payload,
                params=params,
                timeout=self.timeout,
                headers=build_runtime_forward_headers(),
            )
        except requests.RequestException as exc:
            raise PostgresServiceError(
                f"Could not reach postgres-service: {exc}"
            ) from exc

        if response.status_code >= 400:
            raise PostgresServiceError(
                f"postgres-service error {response.status_code}: {response.text}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise PostgresServiceError(
                f"postgres-service returned non-JSON response: {response.text}"
            ) from exc

    def get_processing(self, processing_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/db/document-processing/{processing_id}",
        )

    def get_document(self, document_id: str) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/db/uploaded-documents/{document_id}",
        )

    def get_processing_by_document_id(self, document_id: str) -> dict[str, Any]:
        candidate_requests: list[tuple[str, str, dict[str, Any] | None]] = [
            ("GET", f"/db/document-processing/by-document/{document_id}", None),
            ("GET", f"/db/document-processing/by-document-id/{document_id}", None),
            ("GET", f"/db/document-processing/document/{document_id}", None),
            ("GET", "/db/document-processing", {"document_id": document_id}),
        ]

        last_error: str | None = None

        for method, path, params in candidate_requests:
            try:
                result = self._request(method, path, params=params)
            except PostgresServiceError as exc:
                last_error = str(exc)
                continue

            if isinstance(result, dict) and result.get("processing_id"):
                return result

            if isinstance(result, dict):
                for key in ("data", "processing", "item", "result"):
                    value = result.get(key)
                    if isinstance(value, dict) and value.get("processing_id"):
                        return value

                for key in ("items", "rows", "results", "data"):
                    value = result.get(key)
                    if isinstance(value, list) and value:
                        rows = [row for row in value if isinstance(row, dict) and row.get("processing_id")]
                        if rows:
                            rows.sort(
                                key=lambda row: (
                                    str(row.get("vlm_started_at") or ""),
                                    str(row.get("created_at") or ""),
                                    str(row.get("updated_at") or ""),
                                ),
                                reverse=True,
                            )
                            return rows[0]

            if isinstance(result, list) and result:
                rows = [row for row in result if isinstance(row, dict) and row.get("processing_id")]
                if rows:
                    rows.sort(
                        key=lambda row: (
                            str(row.get("vlm_started_at") or ""),
                            str(row.get("created_at") or ""),
                            str(row.get("updated_at") or ""),
                        ),
                        reverse=True,
                    )
                    return rows[0]

        raise PostgresServiceError(
            "No existing document_processing row was found for "
            f"document_id={document_id}. Last lookup error: {last_error}"
        )

    def patch_processing(
        self,
        processing_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        logger.info(
            "PATCH document_processing | processing_id=%s | keys=%s",
            processing_id,
            list(payload.keys()),
        )

        return self._request(
            "PATCH",
            f"/db/document-processing/{processing_id}",
            json_payload=payload,
        )
