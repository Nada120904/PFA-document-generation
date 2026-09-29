from pathlib import PurePosixPath
from typing import Any

import requests

from ..config import settings
from ..logging import get_logger


logger = get_logger(__name__)


class NextcloudClient:
    def __init__(self):
        self.base_url = (settings.NEXTCLOUD_BASE_URL or settings.STORAGE_URL or "").rstrip("/")
        self.username = settings.NEXTCLOUD_USERNAME or settings.STORAGE_USER
        self.password = settings.NEXTCLOUD_PASSWORD or settings.STORAGE_PASSWORD
        self.verify_tls = bool(settings.STORAGE_VERIFY_TLS)

        if not self.base_url:
            raise RuntimeError("NEXTCLOUD_BASE_URL is required")
        if not self.username:
            raise RuntimeError("NEXTCLOUD_USERNAME is required")
        if not self.password:
            raise RuntimeError("NEXTCLOUD_PASSWORD is required")

    def _auth(self) -> tuple[str, str]:
        return self.username, self.password

    @staticmethod
    def _clean(path: str | None) -> str:
        return str(path or "").strip().replace("\\", "/").strip("/")

    def _url(self, path: str | None) -> str:
        clean_path = self._clean(path)
        return f"{self.base_url}/remote.php/dav/files/{self.username}/{clean_path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        error_label: str,
        headers: dict[str, str] | None = None,
        data: bytes | str | None = None,
        timeout: int = 60,
        ok_status: tuple[int, ...] = (200, 201, 204),
    ) -> requests.Response:
        response = requests.request(
            method=method,
            url=self._url(path),
            headers=headers,
            data=data,
            auth=self._auth(),
            timeout=timeout,
            verify=self.verify_tls,
        )

        if response.status_code not in ok_status:
            logger.error(
                "Nextcloud %s failed: method=%s path=%s status=%s response=%s",
                error_label,
                method,
                path,
                response.status_code,
                response.text,
            )
            raise RuntimeError(
                f"Nextcloud {error_label} error {response.status_code}: {response.text}"
            )

        return response

    def upload_file(
        self,
        folder_path: str,
        file_name: str,
        content: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        folder_path = self._clean(folder_path)
        file_name = self._clean(file_name)
        file_path = f"{folder_path}/{file_name}" if folder_path else file_name

        self._request(
            method="PUT",
            path=file_path,
            error_label="upload",
            data=content,
            timeout=120,
        )

        logger.info("File uploaded to Nextcloud: %s", file_path)

        return {
            "status": "success",
            "message": "File uploaded to Nextcloud",
            "file_path": file_path,
        }

    def download_file(self, file_path: str) -> tuple[bytes, str, str | None]:
        file_path = self._clean(file_path)

        response = self._request(
            method="GET",
            path=file_path,
            error_label="download",
            timeout=120,
        )

        logger.info("File downloaded from Nextcloud: %s", file_path)

        return (
            response.content,
            PurePosixPath(file_path).name,
            response.headers.get("Content-Type"),
        )

    def delete_file(self, file_path: str) -> dict[str, Any]:
        file_path = self._clean(file_path)

        self._request(
            method="DELETE",
            path=file_path,
            error_label="delete",
            ok_status=(200, 204),
        )

        logger.info("File deleted from Nextcloud: %s", file_path)

        return {
            "status": "success",
            "message": "File deleted from Nextcloud",
            "file_path": file_path,
        }

    def create_folder(self, folder_path: str) -> dict[str, Any]:
        folder_path = self._clean(folder_path)

        self._request(
            method="MKCOL",
            path=folder_path,
            error_label="create folder",
            ok_status=(200, 201, 204, 405),
        )

        logger.info("Folder ensured in Nextcloud: %s", folder_path)

        return {
            "status": "success",
            "message": "Folder created in Nextcloud",
            "folder_path": folder_path,
        }

    def copy_file(self, source_path: str, target_path: str) -> dict[str, Any]:
        source_path = self._clean(source_path)
        target_path = self._clean(target_path)

        self._request(
            method="COPY",
            path=source_path,
            error_label="copy",
            headers={
                "Destination": self._url(target_path),
                "Overwrite": "T",
            },
        )

        logger.info("File copied in Nextcloud: %s -> %s", source_path, target_path)

        return {
            "status": "success",
            "source_path": source_path,
            "target_path": target_path,
        }

    def move_file(self, source_path: str, target_path: str) -> dict[str, Any]:
        source_path = self._clean(source_path)
        target_path = self._clean(target_path)

        self._request(
            method="MOVE",
            path=source_path,
            error_label="move",
            headers={
                "Destination": self._url(target_path),
                "Overwrite": "T",
            },
        )

        logger.info("File moved in Nextcloud: %s -> %s", source_path, target_path)

        return {
            "status": "success",
            "source_path": source_path,
            "target_path": target_path,
        }
