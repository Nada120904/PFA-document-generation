from __future__ import annotations

import tempfile
import time
from pathlib import Path

import httpx

from services.docling_service.config import get_settings
from services.docling_service.logging import get_logger
from services.runtime_config import build_runtime_forward_headers


logger = get_logger("rag_system.docling_service.storage_client")

STORAGE_DOWNLOAD_RETRY_ATTEMPTS = 3
STORAGE_DOWNLOAD_RETRY_DELAY_SECONDS = 1.0


class StorageServiceClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.storage_service_url.rstrip("/")
        self.timeout = 120.0

    def download_to_tempfile(
        self,
        *,
        document_id: str,
        file_name: str | None = None,
    ) -> Path:
        def _is_retryable_http_error(exc: Exception) -> bool:
            if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)):
                return True
            if isinstance(exc, httpx.HTTPStatusError) and 500 <= exc.response.status_code <= 599:
                return True
            return False

        last_error: Exception | None = None
        for attempt in range(1, STORAGE_DOWNLOAD_RETRY_ATTEMPTS + 1):
            try:
                response = httpx.get(
                    f"{self.base_url}/storage/download",
                    params={"document_id": document_id},
                    timeout=self.timeout,
                    headers=build_runtime_forward_headers(),
                )
                response.raise_for_status()
                break
            except Exception as exc:
                last_error = exc
                if attempt >= STORAGE_DOWNLOAD_RETRY_ATTEMPTS or not _is_retryable_http_error(exc):
                    raise
                logger.warning(
                    "Retrying storage download for document %s attempt=%s/%s error=%s",
                    document_id,
                    attempt,
                    STORAGE_DOWNLOAD_RETRY_ATTEMPTS,
                    exc,
                )
                time.sleep(STORAGE_DOWNLOAD_RETRY_DELAY_SECONDS)
        else:
            if last_error is not None:
                raise last_error
            raise RuntimeError(f"Storage download retry helper exited unexpectedly for {document_id}.")

        suffix = Path(file_name or document_id).suffix or ".tmp"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(response.content)
            temp_path = Path(handle.name)

        logger.info(
            "Downloaded document %s from storage service to temporary path %s",
            document_id,
            temp_path,
        )
        return temp_path
