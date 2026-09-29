from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from fastapi import HTTPException, UploadFile

from .config import settings
from .logging import get_logger
from .db.postgres_client import PostgresServiceClient
from .providers.factory import get_provider
from .utils.file_helpers import (
    build_uploaded_document_metadata,
    generate_document_id,
)


logger = get_logger(__name__)


class StorageService:
    def __init__(self) -> None:
        self.postgres = PostgresServiceClient()

    def _clean_path(self, path: str | None) -> str:
        return str(path or "").strip().replace("\\", "/").strip("/")

    def _join_path(self, *parts: str | None, keep_leading_slash: bool = False) -> str:
        clean_parts: list[str] = []

        for part in parts:
            if not part:
                continue

            value = str(part).strip().replace("\\", "/").strip("/")
            if value:
                clean_parts.append(value)

        joined_path = str(PurePosixPath(*clean_parts)) if clean_parts else ""

        if keep_leading_slash and joined_path:
            return f"/{joined_path}"

        return joined_path

    def _get_document_or_404(self, document_id: str) -> dict[str, Any]:
        try:
            return self.postgres.get_document(document_id=document_id)
        except HTTPException as exc:
            if exc.status_code == 502:
                detail = exc.detail
                if isinstance(detail, dict) and "404" in str(detail.get("status_code", "")):
                    raise HTTPException(
                        status_code=404,
                        detail=f"Document not found: {document_id}",
                    ) from exc

            raise

    def _get_upload_folder(self, provider: str) -> str:
        if provider == "onedrive":
            return self._join_path(
                settings.ONEDRIVE_ROOT_FOLDER,
                settings.ONEDRIVE_UPLOAD_FOLDER,
            )

        if provider == "sharepoint":
            return self._join_path(
                settings.SHAREPOINT_FOLDER,
                settings.SHAREPOINT_UPLOAD_FOLDER,
                keep_leading_slash=True,
            )

        if provider == "nextcloud":
            return self._join_path(
                settings.NEXTCLOUD_ROOT_PATH,
                settings.NEXTCLOUD_UPLOAD_FOLDER,
            )

        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider: {provider}",
        )

    def _get_processed_folder(
        self,
        provider: str,
        folder_name: str | None = None,
    ) -> str:
        if provider == "onedrive":
            base_folder = self._join_path(
                settings.ONEDRIVE_ROOT_FOLDER,
                settings.ONEDRIVE_PROCESSED_FOLDER,
            )

        elif provider == "sharepoint":
            base_folder = self._join_path(
                settings.SHAREPOINT_FOLDER,
                settings.SHAREPOINT_PROCESSED_FOLDER,
                keep_leading_slash=True,
            )

        elif provider == "nextcloud":
            base_folder = self._join_path(
                settings.NEXTCLOUD_ROOT_PATH,
                settings.NEXTCLOUD_PROCESSED_FOLDER,
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported provider: {provider}",
            )

        if folder_name:
            return self._join_path(base_folder, self._clean_path(folder_name))

        return base_folder

    def _build_list_folder_path(
        self,
        provider: str,
        folder_type: str,
        folder_name: str | None = None,
    ) -> str:
        folder_type = self._clean_path(folder_type).lower()

        if folder_type == "raw":
            return self._get_upload_folder(provider)

        if folder_type == "processed":
            return self._get_processed_folder(
                provider=provider,
                folder_name=folder_name,
            )

        raise HTTPException(
            status_code=400,
            detail="folder_type must be 'raw' or 'processed'",
        )

    def _build_document_file_path(self, provider: str, storage_path: str) -> str:
        clean_path = str(storage_path or "").strip().replace("\\", "/").strip("/")

        if provider == "nextcloud":
            if not settings.NEXTCLOUD_BASE_URL:
                raise RuntimeError("NEXTCLOUD_BASE_URL is required")

            if not settings.NEXTCLOUD_USERNAME:
                raise RuntimeError("NEXTCLOUD_USERNAME is required")

            base_url = settings.NEXTCLOUD_BASE_URL.rstrip("/")
            username = settings.NEXTCLOUD_USERNAME

            return f"{base_url}/remote.php/dav/files/{username}/{clean_path}"

        if provider == "sharepoint":
            return f"/{clean_path}"

        if provider == "onedrive":
            return clean_path

        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider: {provider}",
        )

    def _provider_path_from_document_path(self, provider: str, file_path: str) -> str:
        clean_path = str(file_path or "").strip().replace("\\", "/")

        if provider == "nextcloud":
            if settings.NEXTCLOUD_BASE_URL and settings.NEXTCLOUD_USERNAME:
                prefix = (
                    f"{settings.NEXTCLOUD_BASE_URL.rstrip('/')}"
                    f"/remote.php/dav/files/{settings.NEXTCLOUD_USERNAME}/"
                )

                if clean_path.startswith(prefix):
                    return clean_path.replace(prefix, "", 1).strip("/")

            return clean_path.strip("/")

        if provider == "sharepoint":
            return clean_path if clean_path.startswith("/") else f"/{clean_path.strip('/')}"

        if provider == "onedrive":
            return clean_path.strip("/")

        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider: {provider}",
        )
    def _save_operation(
        self,
        operation: str,
        document_id: str | None = None,
        storage_backend: str | None = None,
        source_path: str | None = None,
        target_path: str | None = None,
        folder_name: str | None = None,
        operation_status: str = "success",
        error_message: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            "operation_id": None,
            "operation": operation,
            "document_id": document_id,
            "storage_backend": storage_backend,
            "source_path": source_path,
            "target_path": target_path,
            "folder_name": folder_name,
            "operation_status": operation_status,
            "error_message": error_message,
        }
        if operation_status == "success":
            logger.info("Storage operation completed: %s", payload)
        else:
            logger.warning("Storage operation failed: %s", payload)
        return payload

    def _ensure_processed_folder_exists(self, provider: str, folder_name: str) -> None:
        storage_provider = get_provider(provider)
        clean_folder_name = self._clean_path(folder_name)

        if not clean_folder_name:
            return

        current_folder = ""

        for part in clean_folder_name.split("/"):
            part = part.strip()

            if not part:
                continue

            current_folder = self._join_path(current_folder, part)

            target_provider_path = self._get_processed_folder(
                provider=provider,
                folder_name=current_folder,
            )

            storage_provider.create_folder(folder_path=target_provider_path)

    def _list_documents_from_db(
        self,
        provider: str,
        folder_path: str,
    ) -> list[dict[str, Any]]:
        document_folder_path = self._build_document_file_path(
            provider=provider,
            storage_path=folder_path,
        )

        return self.postgres.list_storage_documents(
            storage_backend=provider,
            file_path_prefix=document_folder_path,
            exclude_status="deleted",
            limit=500,
        )

    def upload_file(
        self,
        provider: str,
        file: UploadFile,
        metadata_json: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        storage_provider = get_provider(provider)
        folder_path = self._get_upload_folder(provider)

        content = file.file.read()
        metadata = build_uploaded_document_metadata(file=file, content=content)

        file_name = metadata["file_name"]
        storage_path = self._join_path(folder_path, file_name)
        document_file_path = self._build_document_file_path(provider, storage_path)

        try:
            storage_provider.upload_file(
                folder_path=folder_path,
                file_name=file_name,
                content=content,
                content_type=metadata["mime_type"],
            )

            document = self.postgres.create_document(
                document_id=metadata["document_id"],
                storage_backend=provider,
                file_name=file_name,
                file_path=document_file_path,
                mime_type=metadata["mime_type"],
                doc_type=metadata["doc_type"],
                file_hash=metadata["file_hash"],
                metadata_json=metadata_json,
                status="stored",
            )

            self._save_operation(
                operation="upload",
                document_id=document["document_id"],
                storage_backend=provider,
                target_path=document["file_path"],
                operation_status="success",
            )

            logger.info(
                "File uploaded and registered: provider=%s document_id=%s file_name=%s",
                provider,
                document["document_id"],
                document["file_name"],
            )

            return {
                "status": "success",
                "operation": "upload",
                "provider": provider,
                "document_id": document["document_id"],
                "file_name": document["file_name"],
                "file_path": document["file_path"],
                "mime_type": document.get("mime_type"),
                "doc_type": document.get("doc_type"),
                "file_hash": document.get("file_hash"),
                "metadata_json": document.get("metadata_json"),
            }

        except Exception as exc:
            logger.error(
                "Upload failed: provider=%s file_name=%s error=%s",
                provider,
                file_name,
                exc,
            )

            self._save_operation(
                operation="upload",
                document_id=None,
                storage_backend=provider,
                target_path=document_file_path,
                operation_status="failed",
                error_message=str(exc),
            )

            raise

    def download_file_by_id(self, document_id: str) -> tuple[bytes, str, str | None]:
        document = self._get_document_or_404(document_id)
        provider = document["storage_backend"]
        storage_provider = get_provider(provider)

        provider_file_path = self._provider_path_from_document_path(
            provider=provider,
            file_path=document["file_path"],
        )

        logger.info(
            "Downloading file: provider=%s document_id=%s",
            provider,
            document["document_id"],
        )

        return storage_provider.download_file(file_path=provider_file_path)

    def get_file_info_by_id(self, document_id: str) -> dict[str, Any]:
        document = self._get_document_or_404(document_id)

        return {
            "status": "success",
            "operation": "info",
            "provider": document["storage_backend"],
            "document_id": document["document_id"],
            "file_name": document["file_name"],
            "file_path": document["file_path"],
            "mime_type": document.get("mime_type"),
            "doc_type": document.get("doc_type"),
            "file_hash": document.get("file_hash"),
            "metadata_json": document.get("metadata_json"),
            "document_status": document.get("status"),
            "created_at": document.get("created_at"),
            "updated_at": document.get("updated_at"),
        }

    def delete_file_by_id(self, document_id: str) -> dict[str, Any]:
        document = self._get_document_or_404(document_id)
        provider = document["storage_backend"]
        storage_provider = get_provider(provider)

        provider_file_path = self._provider_path_from_document_path(
            provider=provider,
            file_path=document["file_path"],
        )

        try:
            storage_provider.delete_file(file_path=provider_file_path)

            updated_document = self.postgres.update_document(
                document_id=document_id,
                payload={"status": "deleted"},
            )

            operation_record = self._save_operation(
                operation="delete",
                document_id=updated_document["document_id"],
                storage_backend=provider,
                source_path=document["file_path"],
                operation_status="success",
            )

            logger.info(
                "File deleted: provider=%s document_id=%s",
                provider,
                document_id,
            )

            return {
                "status": "success",
                "operation": "delete",
                "provider": provider,
                "operation_id": operation_record["operation_id"],
                "document_id": updated_document["document_id"],
                "file_path": updated_document["file_path"],
                "message": "File deleted successfully",
            }

        except Exception as exc:
            logger.error(
                "Delete failed: document_id=%s provider=%s error=%s",
                document_id,
                provider,
                exc,
            )

            self._save_operation(
                operation="delete",
                document_id=document_id,
                storage_backend=provider,
                source_path=document["file_path"],
                operation_status="failed",
                error_message=str(exc),
            )

            raise

    def move_file_to_processed_folder(
        self,
        document_id: str,
        target_folder_name: str,
    ) -> dict[str, Any]:
        document = self._get_document_or_404(document_id)
        provider = document["storage_backend"]
        storage_provider = get_provider(provider)

        source_document_path = document["file_path"]

        source_provider_path = self._provider_path_from_document_path(
            provider=provider,
            file_path=document["file_path"],
        )

        clean_target_folder_name = self._clean_path(target_folder_name)

        self._ensure_processed_folder_exists(
            provider=provider,
            folder_name=clean_target_folder_name,
        )

        target_provider_folder = self._get_processed_folder(
            provider=provider,
            folder_name=clean_target_folder_name,
        )

        target_provider_path = self._join_path(
            target_provider_folder,
            document["file_name"],
        )

        target_document_path = self._build_document_file_path(
            provider=provider,
            storage_path=target_provider_path,
        )

        try:
            storage_provider.move_file(
                source_path=source_provider_path,
                target_path=target_provider_path,
            )

            updated_document = self.postgres.update_document(
                document_id=document_id,
                payload={
                    "file_path": target_document_path,
                    "status": "moved",
                },
            )

            operation_record = self._save_operation(
                operation="move",
                document_id=updated_document["document_id"],
                storage_backend=provider,
                source_path=source_document_path,
                target_path=target_document_path,
                folder_name=clean_target_folder_name,
                operation_status="success",
            )

            logger.info(
                "File moved: provider=%s document_id=%s target=%s",
                provider,
                document_id,
                target_document_path,
            )

            return {
                "status": "success",
                "operation": "move",
                "provider": provider,
                "operation_id": operation_record["operation_id"],
                "document_id": updated_document["document_id"],
                "source_path": source_document_path,
                "target_path": target_document_path,
                "folder_name": clean_target_folder_name,
                "message": "File moved successfully",
            }

        except Exception as exc:
            logger.error(
                "Move failed: document_id=%s provider=%s target=%s error=%s",
                document_id,
                provider,
                target_document_path,
                exc,
            )

            self._save_operation(
                operation="move",
                document_id=document_id,
                storage_backend=provider,
                source_path=source_document_path,
                target_path=target_document_path,
                folder_name=clean_target_folder_name,
                operation_status="failed",
                error_message=str(exc),
            )

            raise

    def copy_file_to_processed_folder(
        self,
        document_id: str,
        target_folder_name: str,
    ) -> dict[str, Any]:
        source_document = self._get_document_or_404(document_id)
        provider = source_document["storage_backend"]
        storage_provider = get_provider(provider)

        source_document_path = source_document["file_path"]

        source_provider_path = self._provider_path_from_document_path(
            provider=provider,
            file_path=source_document["file_path"],
        )

        clean_target_folder_name = self._clean_path(target_folder_name)

        self._ensure_processed_folder_exists(
            provider=provider,
            folder_name=clean_target_folder_name,
        )

        target_provider_folder = self._get_processed_folder(
            provider=provider,
            folder_name=clean_target_folder_name,
        )

        target_provider_path = self._join_path(
            target_provider_folder,
            source_document["file_name"],
        )

        target_document_path = self._build_document_file_path(
            provider=provider,
            storage_path=target_provider_path,
        )

        try:
            storage_provider.copy_file(
                source_path=source_provider_path,
                target_path=target_provider_path,
            )

            copied_document = self.postgres.create_document(
                document_id=generate_document_id(),
                storage_backend=provider,
                file_name=source_document["file_name"],
                file_path=target_document_path,
                mime_type=source_document.get("mime_type"),
                doc_type=source_document.get("doc_type"),
                file_hash=source_document.get("file_hash"),
                status="copied",
            )

            operation_record = self._save_operation(
                operation="copy",
                document_id=copied_document["document_id"],
                storage_backend=provider,
                source_path=source_document_path,
                target_path=target_document_path,
                folder_name=clean_target_folder_name,
                operation_status="success",
            )

            logger.info(
                "File copied: provider=%s source_document_id=%s copied_document_id=%s",
                provider,
                source_document["document_id"],
                copied_document["document_id"],
            )

            return {
                "status": "success",
                "operation": "copy",
                "provider": provider,
                "operation_id": operation_record["operation_id"],
                "document_id": copied_document["document_id"],
                "source_path": source_document_path,
                "target_path": target_document_path,
                "folder_name": clean_target_folder_name,
                "message": "File copied successfully",
            }

        except Exception as exc:
            logger.error(
                "Copy failed: document_id=%s provider=%s target=%s error=%s",
                source_document["document_id"],
                provider,
                target_document_path,
                exc,
            )

            self._save_operation(
                operation="copy",
                document_id=source_document["document_id"],
                storage_backend=provider,
                source_path=source_document_path,
                target_path=target_document_path,
                folder_name=clean_target_folder_name,
                operation_status="failed",
                error_message=str(exc),
            )

            raise

    def create_processed_folder(
        self,
        provider: str,
        folder_name: str,
    ) -> dict[str, Any]:
        clean_folder_name = self._clean_path(folder_name)

        if not clean_folder_name:
            raise HTTPException(
                status_code=400,
                detail="folder_name is required",
            )

        try:
            self._ensure_processed_folder_exists(
                provider=provider,
                folder_name=clean_folder_name,
            )

            target_provider_path = self._get_processed_folder(
                provider=provider,
                folder_name=clean_folder_name,
            )

            target_document_path = self._build_document_file_path(
                provider=provider,
                storage_path=target_provider_path,
            )

            operation_record = self._save_operation(
                operation="create_folder",
                document_id=None,
                storage_backend=provider,
                target_path=target_document_path,
                folder_name=clean_folder_name,
                operation_status="success",
            )

            logger.info(
                "Processed folder ensured: provider=%s path=%s",
                provider,
                target_document_path,
            )

            return {
                "status": "success",
                "operation": "create_folder",
                "provider": provider,
                "operation_id": operation_record["operation_id"],
                "target_path": target_document_path,
                "folder_name": clean_folder_name,
                "message": "Processed folder created successfully",
            }

        except Exception as exc:
            logger.error(
                "Create folder failed: provider=%s folder=%s error=%s",
                provider,
                clean_folder_name,
                exc,
            )

            self._save_operation(
                operation="create_folder",
                document_id=None,
                storage_backend=provider,
                target_path=None,
                folder_name=clean_folder_name,
                operation_status="failed",
                error_message=str(exc),
            )

            raise

    def list_files_by_type(
        self,
        provider: str,
        folder_type: str,
        folder_name: str | None = None,
    ) -> dict[str, Any]:
        folder_path = self._build_list_folder_path(
            provider=provider,
            folder_type=folder_type,
            folder_name=folder_name,
        )

        items = self._list_documents_from_db(
            provider=provider,
            folder_path=folder_path,
        )

        return {
            "status": "success",
            "operation": "list",
            "provider": provider,
            "folder_path": self._build_document_file_path(provider, folder_path),
            "items": items,
        }

    def build_processed_target_path(
        self,
        provider: str,
        file_name: str,
        folder_name: str | None = None,
    ) -> str:
        processed_folder = self._get_processed_folder(
            provider=provider,
            folder_name=folder_name,
        )

        return self._join_path(processed_folder, file_name)
