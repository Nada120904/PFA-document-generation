from abc import ABC, abstractmethod
from typing import Any


class StorageProvider(ABC):
    @abstractmethod
    def upload_file(
        self,
        folder_path: str,
        file_name: str,
        content: bytes,
        content_type: str | None = None,
    ) -> dict[str, Any]:
        pass

    @abstractmethod
    def download_file(self, file_path: str) -> tuple[bytes, str, str | None]:
        pass

    @abstractmethod
    def delete_file(self, file_path: str) -> dict[str, Any]:
        pass

    @abstractmethod
    def move_file(self, source_path: str, target_path: str) -> dict[str, Any]:
        pass

    @abstractmethod
    def copy_file(self, source_path: str, target_path: str) -> dict[str, Any]:
        pass

    @abstractmethod
    def create_folder(self, folder_path: str) -> dict[str, Any]:
        pass