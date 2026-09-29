from pathlib import Path

import requests

from ..config import settings
from ..logging import get_logger


logger = get_logger(__name__)


class GraphAuthError(Exception):
    pass


class GraphAuth:
    def _token_path(self) -> Path:
        token_path = Path(settings.ONEDRIVE_REFRESH_TOKEN_FILE)

        if token_path.is_absolute():
            return token_path

        # Resolve relative token paths from the storage_service root.
        # Works both locally and inside the Docker image (/service).
        service_root = Path(__file__).resolve().parents[2]
        return service_root / token_path

    def load_refresh_token(self) -> str:
        direct_token = (settings.ONEDRIVE_REFRESH_TOKEN or "").strip()
        if direct_token:
            return direct_token

        token_path = self._token_path()

        if not token_path.exists():
            raise GraphAuthError(f"Refresh token file not found: {token_path}")

        token = token_path.read_text(encoding="utf-8").strip()

        if not token:
            raise GraphAuthError(f"Refresh token file is empty: {token_path}")

        return token

    def save_refresh_token(self, token: str) -> None:
        token_path = self._token_path()
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(token, encoding="utf-8")

    def get_access_token(self) -> str:
        if not settings.ONEDRIVE_CLIENT_ID:
            raise GraphAuthError("ONEDRIVE_CLIENT_ID is required")

        if not settings.ONEDRIVE_CLIENT_SECRET:
            raise GraphAuthError("ONEDRIVE_CLIENT_SECRET is required")

        refresh_token = self.load_refresh_token()
        token_url = f"{settings.ONEDRIVE_AUTHORITY}/oauth2/v2.0/token"

        data = {
            "client_id": settings.ONEDRIVE_CLIENT_ID,
            "client_secret": settings.ONEDRIVE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
            "scope": "offline_access Files.ReadWrite User.Read",
        }

        response = requests.post(token_url, data=data, timeout=60)

        try:
            payload = response.json()
        except ValueError as exc:
            logger.error("Invalid Microsoft token response: %s", response.text)
            raise GraphAuthError(
                f"Graph token error {response.status_code}: {response.text}"
            ) from exc

        if response.status_code >= 400:
            logger.error("Microsoft Graph token error: %s", payload)
            raise GraphAuthError(
                f"Graph token error {response.status_code}: {payload}"
            )

        access_token = payload.get("access_token")
        new_refresh_token = payload.get("refresh_token")

        if not access_token:
            raise GraphAuthError("No access_token returned from Microsoft")

        if new_refresh_token:
            self.save_refresh_token(new_refresh_token)
            logger.info("OneDrive refresh token updated successfully")

        return access_token
