from __future__ import annotations

import tempfile
from pathlib import Path

import requests

from app.config import get_settings
from app.logging import get_logger
from app.runtime_config import build_runtime_forward_headers


logger = get_logger(__name__)


class StorageServiceClient:
    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.storage_service_url.rstrip("/")
        self.timeout = settings.request_timeout_seconds

    def download_to_tempfile(
        self,
        document_id: str,
        file_name: str | None = None,
    ) -> Path:
        response = requests.get(
            f"{self.base_url}/storage/download",
            params={"document_id": document_id},
            timeout=self.timeout,
            headers=build_runtime_forward_headers(),
        )
        response.raise_for_status()

        suffix = Path(file_name or "").suffix or ".tmp"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(response.content)
            temp_path = Path(handle.name)

        logger.info(
            "Downloaded document %s from storage-service to %s",
            document_id,
            temp_path,
        )

        return temp_path
