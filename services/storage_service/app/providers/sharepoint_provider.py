import base64
from pathlib import PurePosixPath
from typing import Any

from ..clients.powerautomate_client import PowerAutomateClient
from .base import StorageProvider


class SharePointProvider(StorageProvider):
    def __init__(self):
        self.client = PowerAutomateClient()

    @staticmethod
    def _clean_path(path: str) -> str:
        return str(path or "").strip().replace("\\", "/").strip("/")

    @staticmethod
    def _to_server_relative_path(path: str) -> str:
        clean_path = str(path or "").strip().replace("\\", "/")
        return clean_path if clean_path.startswith("/") else f"/{clean_path.strip('/')}"

    @staticmethod
    def _to_library_relative_path(path: str) -> str:
        clean_path = SharePointProvider._clean_path(path)

        if "Shared Documents/" in clean_path:
            return clean_path.split("Shared Documents/", 1)[1]

        return clean_path

    @staticmethod
    def _to_connector_file_path(path: str) -> str:
        clean_path = SharePointProvider._clean_path(path)

        if "Shared Documents/" in clean_path:
            return "/Shared Documents/" + clean_path.split("Shared Documents/", 1)[1]

        return f"/{clean_path}"

    @staticmethod
    def _to_connector_folder_path(path: str) -> str:
        connector_file_path = SharePointProvider._to_connector_file_path(path)
        return str(PurePosixPath(connector_file_path).parent)

    def upload_file(
        self,
        folder_path: str,
        file_name: str,
        content: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        return self.client.call({
            "operation": "upload",
            "folder_path": self._to_library_relative_path(folder_path),
            "file_name": file_name,
            "content_type": content_type,
            "content_base64": base64.b64encode(content).decode("utf-8"),
        })

    def download_file(self, file_path: str) -> tuple[bytes, str, str | None]:
        result = self.client.call({
            "operation": "download",
            "file_path": self._to_connector_file_path(file_path),
            "server_relative_path": self._to_server_relative_path(file_path),
        })

        content_base64 = result.get("content_base64")

        if not content_base64:
            raise RuntimeError("Power Automate response missing content_base64")

        content = base64.b64decode(content_base64)
        file_name = result.get("file_name") or PurePosixPath(file_path).name
        content_type = result.get("content_type") or "application/octet-stream"

        return content, file_name, content_type

    def delete_file(self, file_path: str) -> dict[str, Any]:
        return self.client.call({
            "operation": "delete",
            "file_path": self._to_connector_file_path(file_path),
            "server_relative_path": self._to_server_relative_path(file_path),
        })

    def move_file(self, source_path: str, target_path: str) -> dict[str, Any]:
        return self.client.call({
            "operation": "move",
            "source_path": self._to_connector_file_path(source_path),
            "target_path": self._to_connector_file_path(target_path),
            "target_folder_path": self._to_connector_folder_path(target_path),
            "server_relative_source_path": self._to_server_relative_path(source_path),
            "server_relative_target_path": self._to_server_relative_path(target_path),
        })

    def copy_file(self, source_path: str, target_path: str) -> dict[str, Any]:
        return self.client.call({
            "operation": "copy",
            "source_path": self._to_connector_file_path(source_path),
            "target_path": self._to_connector_file_path(target_path),
            "target_folder_path": self._to_connector_folder_path(target_path),
            "server_relative_source_path": self._to_server_relative_path(source_path),
            "server_relative_target_path": self._to_server_relative_path(target_path),
        })

    def create_folder(self, folder_path: str) -> dict[str, Any]:
        return self.client.call({
            "operation": "create_folder",
            "folder_path": self._to_library_relative_path(folder_path),
            "server_relative_path": self._to_server_relative_path(folder_path),
        })