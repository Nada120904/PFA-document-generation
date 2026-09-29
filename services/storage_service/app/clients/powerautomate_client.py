from typing import Any

import requests

from ..config import settings
from ..logging import get_logger


logger = get_logger(__name__)


class PowerAutomateClient:
    def __init__(self):
        if not settings.SHAREPOINT_POWER_AUTOMATE_URL:
            raise RuntimeError("SHAREPOINT_POWER_AUTOMATE_URL is required")

        self.url = settings.SHAREPOINT_POWER_AUTOMATE_URL

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        operation = payload.get("operation", "unknown")
        response = requests.post(self.url,json=payload,headers={"Content-Type": "application/json"},timeout=120,)
        if response.status_code >= 400:
            logger.error(
                "Power Automate operation failed: operation=%s status=%s response=%s",
                operation,
                response.status_code,
                response.text,
            )
            raise RuntimeError(
                f"Power Automate error {response.status_code}: {response.text}"
            )

        if not response.text:
            return {"status": "success", "operation": operation}

        try:
            return response.json()
        except ValueError:
            logger.warning(
                "Power Automate returned non-JSON response: operation=%s response=%s",
                operation,
                response.text,
            )
            return {
                "status": "success",
                "operation": operation,
                "raw_response": response.text,
            }