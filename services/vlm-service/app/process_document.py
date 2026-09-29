from __future__ import annotations

import datetime
import time
from pathlib import Path
from typing import Any

from app.logging import get_logger
from app.postgres_client import PostgresClient
from app.runtime_config import use_runtime_overrides
from app.storage_client import StorageServiceClient
from app.vlm_client import VLMClient


logger = get_logger(__name__)


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def to_iso(dt: datetime.datetime) -> str:
    return dt.isoformat()


class ProcessDocumentService:
    def __init__(self) -> None:
        self.postgres = PostgresClient()
        self.storage = StorageServiceClient()
        self.vlm = VLMClient()

    def _resolve_input_file(
        self,
        document_id: str,
        file_name: str | None = None,
    ) -> tuple[Path, bool]:
        return (
            self.storage.download_to_tempfile(
                document_id=document_id,
                file_name=file_name,
            ),
            True,
        )

    def enqueue_processing(self, processing_id: str) -> dict[str, Any]:
        processing = self.postgres.get_processing(processing_id)
        document_id = processing["document_id"]

        self.postgres.patch_processing(
            processing_id,
            {
                "processing_status": "pending",
                "used_vlm": True,
                "vlm_model": self.vlm.model_id,
                "vlm_started_at": None,
                "vlm_processing_time": None,
            },
        )

        return {
            "processing_id": processing_id,
            "document_id": document_id,
            "status": "pending",
            "message": "VLM processing scheduled in background.",
        }

    def enqueue_processing_by_document_id(self, document_id: str) -> dict[str, Any]:
        document = self.postgres.get_document(document_id)
        processing = self.postgres.get_processing_by_document_id(document_id)
        processing_id = processing["processing_id"]

        self.postgres.patch_processing(
            processing_id,
            {
                "processing_status": "pending",
                "used_vlm": True,
                "vlm_model": self.vlm.model_id,
                "vlm_started_at": None,
                "vlm_processing_time": None,
            },
        )

        logger.info(
            "VLM processing scheduled from existing document_processing row | document_id=%s | processing_id=%s | file_name=%s",
            document_id,
            processing_id,
            document.get("file_name"),
        )

        return {
            "processing_id": processing_id,
            "document_id": document_id,
            "status": "pending",
            "message": "VLM processing scheduled in background using existing processing row.",
        }

    def process_in_background(
        self,
        processing_id: str,
        runtime_overrides: dict[str, str] | None = None,
    ) -> None:
        with use_runtime_overrides(runtime_overrides):
            # Recreate clients inside the runtime-override context so per-request
            # headers like x-rag-vlm-model-id actually affect the background job.
            self.postgres = PostgresClient()
            self.storage = StorageServiceClient()
            self.vlm = VLMClient()
            start_time = time.perf_counter()
            started_at = utc_now()

            try:
                processing = self.postgres.get_processing(processing_id)
                document_id = processing["document_id"]

                document = self.postgres.get_document(document_id)
                file_path = document["file_path"]
                file_name = document.get("file_name")
                local_path, is_temp_file = self._resolve_input_file(
                    document_id=document_id,
                    file_name=file_name,
                )

                logger.info(
                    "Starting background VLM processing | processing_id=%s | document_id=%s | file_path=%s",
                    processing_id,
                    document_id,
                    file_path,
                )

                self.postgres.patch_processing(
                    processing_id,
                    {
                        "processing_status": "running",
                        "used_vlm": True,
                        "vlm_model": self.vlm.model_id,
                        "vlm_started_at": to_iso(started_at),
                    },
                )

                result = self.vlm.extract_markdown_text(file_path=str(local_path))

                elapsed = round(time.perf_counter() - start_time, 3)

                self.postgres.patch_processing(
                    processing_id,
                    {
                        "processing_status": "completed",
                        "used_vlm": True,
                        "vlm_model": result["model_id"],
                        "markdown_text": result["markdown_text"],
                        "vlm_processing_time": elapsed,
                    },
                )

                logger.info(
                    "VLM processing completed | processing_id=%s | chars=%d | time=%.3fs",
                    processing_id,
                    result["characters"],
                    elapsed,
                )

            except Exception as exc:
                elapsed = round(time.perf_counter() - start_time, 3)

                logger.error(
                    "VLM processing failed | processing_id=%s | error=%s",
                    processing_id,
                    exc,
                    exc_info=True,
                )

                try:
                    failure_payload = {
                        "processing_status": "vlm_error",
                        "used_vlm": True,
                        "vlm_model": self.vlm.model_id,
                        "vlm_processing_time": elapsed,
                    }

                    try:
                        self.postgres.patch_processing(
                            processing_id,
                            failure_payload,
                        )
                    except Exception as status_exc:
                        logger.warning(
                            "Could not set processing_status=vlm_error. Falling back to failed | processing_id=%s | error=%s",
                            processing_id,
                            status_exc,
                        )

                        failure_payload["processing_status"] = "failed"
                        self.postgres.patch_processing(
                            processing_id,
                            failure_payload,
                        )

                except Exception as update_exc:
                    logger.error(
                        "Could not update failed processing status | processing_id=%s | error=%s",
                        processing_id,
                        update_exc,
                        exc_info=True,
                    )

            finally:
                if "is_temp_file" in locals() and is_temp_file and "local_path" in locals():
                    local_path.unlink(missing_ok=True)
                    logger.info("Deleted temporary VLM file %s", local_path)

    def check_processing(self, processing_id: str) -> dict[str, Any]:
        processing = self.postgres.get_processing(processing_id)

        markdown_text = processing.get("markdown_text") or ""

        return {
            "processing_id": processing["processing_id"],
            "document_id": processing["document_id"],
            "processing_status": processing["processing_status"],
            "used_vlm": processing.get("used_vlm"),
            "vlm_model": processing.get("vlm_model"),
            "vlm_started_at": processing.get("vlm_started_at"),
            "vlm_processing_time": processing.get("vlm_processing_time"),
            "markdown_text_available": bool(markdown_text),
            "markdown_text_length": len(markdown_text),
            "raw_processing": processing,
        }
