from typing import Any

from ..clients.nextcloud_client import NextcloudClient
from .base import StorageProvider


class NextcloudProvider(StorageProvider):
    def __init__(self):
        self.client = NextcloudClient()

    def upload_file(
        self,
        folder_path: str,
        file_name: str,
        content: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        return self.client.upload_file(folder_path, file_name, content, content_type)

    def download_file(self, file_path: str) -> tuple[bytes, str, str | None]:
        return self.client.download_file(file_path)

    def delete_file(self, file_path: str) -> dict[str, Any]:
        return self.client.delete_file(file_path)

    def move_file(self, source_path: str, target_path: str) -> dict[str, Any]:
        return self.client.move_file(source_path, target_path)

    def copy_file(self, source_path: str, target_path: str) -> dict[str, Any]:
        return self.client.copy_file(source_path, target_path)

    def create_folder(self, folder_path: str) -> dict[str, Any]:
        return self.client.create_folder(folder_path)