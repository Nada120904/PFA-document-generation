from pathlib import PurePosixPath
from typing import Any

import requests

from .graph_auth import GraphAuth
from ..config import settings
from ..logging import get_logger


logger = get_logger(__name__)


class GraphClient:
    def __init__(self):
        self.base_url = settings.GRAPH_BASE_URL.rstrip("/")
        self.auth = GraphAuth()

    def _headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.auth.get_access_token()}"}

        if content_type:
            headers["Content-Type"] = content_type

        return headers

    @staticmethod
    def _clean(path: str | None) -> str:
        return str(path or "").strip().replace("\\", "/").strip("/")

    def _item_url(self, file_path: str) -> str:
        file_path = self._clean(file_path)
        return f"{self.base_url}/me/drive/root:/{file_path}"

    def _content_url(self, file_path: str) -> str:
        file_path = self._clean(file_path)
        return f"{self.base_url}/me/drive/root:/{file_path}:/content"

    def _children_url(self, folder_path: str | None = None) -> str:
        folder_path = self._clean(folder_path)

        if folder_path:
            return f"{self.base_url}/me/drive/root:/{folder_path}:/children"

        return f"{self.base_url}/me/drive/root/children"

    def _request(
        self,
        method: str,
        url: str,
        error_label: str,
        *,
        json: dict[str, Any] | None = None,
        data: bytes | None = None,
        content_type: str | None = None,
        timeout: int = 60,
    ) -> requests.Response:
        response = requests.request(
            method=method,
            url=url,
            headers=self._headers(content_type),
            json=json,
            data=data,
            timeout=timeout,
        )

        if response.status_code >= 400:
            logger.error(
                "OneDrive %s failed: status=%s response=%s",
                error_label,
                response.status_code,
                response.text,
            )
            raise RuntimeError(
                f"OneDrive {error_label} error {response.status_code}: {response.text}"
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

        response = self._request(
            method="PUT",
            url=self._content_url(file_path),
            error_label="upload",
            data=content,
            content_type=content_type or "application/octet-stream",
            timeout=120,
        )

        logger.info("File uploaded to OneDrive: %s", file_path)

        return response.json()

    def download_file(self, file_path: str) -> tuple[bytes, str, str | None]:
        clean_path = self._clean(file_path)

        response = self._request(
            method="GET",
            url=self._content_url(clean_path),
            error_label="download",
            timeout=120,
        )

        logger.info("File downloaded from OneDrive: %s", clean_path)

        return (
            response.content,
            PurePosixPath(clean_path).name,
            response.headers.get("Content-Type"),
        )

    def delete_file(self, file_path: str) -> dict[str, Any]:
        clean_path = self._clean(file_path)

        self._request(
            method="DELETE",
            url=self._item_url(clean_path),
            error_label="delete",
        )

        logger.info("File deleted from OneDrive: %s", clean_path)

        return {
            "status": "success",
            "message": "File deleted from OneDrive",
            "file_path": clean_path,
        }

    def create_folder(self, folder_path: str) -> dict[str, Any]:
        folder_path = self._clean(folder_path)

        parent_path = str(PurePosixPath(folder_path).parent).strip(".")
        folder_name = PurePosixPath(folder_path).name

        payload = {
            "name": folder_name,
            "folder": {},
            "@microsoft.graph.conflictBehavior": "replace",
        }

        self._request(
            method="POST",
            url=self._children_url(parent_path),
            error_label="create folder",
            json=payload,
            content_type="application/json",
        )

        logger.info("Folder ensured in OneDrive: %s", folder_path)

        return {
            "status": "success",
            "message": "Folder created in OneDrive",
            "folder_path": folder_path,
        }

    def copy_file(self, source_path: str, target_path: str) -> dict[str, Any]:
        source_path = self._clean(source_path)
        target_path = self._clean(target_path)

        target_folder = str(PurePosixPath(target_path).parent).strip(".")
        target_name = PurePosixPath(target_path).name

        payload = {
            "parentReference": {
                "path": f"/drive/root:/{target_folder}",
            },
            "name": target_name,
        }

        self._request(
            method="POST",
            url=f"{self._item_url(source_path)}:/copy",
            error_label="copy",
            json=payload,
            content_type="application/json",
        )

        logger.info("Copy started in OneDrive: %s -> %s", source_path, target_path)

        return {
            "status": "success",
            "message": "Copy started in OneDrive",
            "source_path": source_path,
            "target_path": target_path,
        }

    def move_file(self, source_path: str, target_path: str) -> dict[str, Any]:
        source_path = self._clean(source_path)
        target_path = self._clean(target_path)

        target_folder = str(PurePosixPath(target_path).parent).strip(".")
        target_name = PurePosixPath(target_path).name

        payload = {
            "parentReference": {
                "path": f"/drive/root:/{target_folder}",
            },
            "name": target_name,
        }

        self._request(
            method="PATCH",
            url=self._item_url(source_path),
            error_label="move",
            json=payload,
            content_type="application/json",
        )

        logger.info("File moved in OneDrive: %s -> %s", source_path, target_path)

        return {
            "status": "success",
            "message": "File moved in OneDrive",
            "source_path": source_path,
            "target_path": target_path,
        }