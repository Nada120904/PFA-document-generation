"""HTTP helpers for calling internal backend services."""

from __future__ import annotations

import json
import os
import time
from urllib import error, parse, request

from services.runtime_config import (
    build_runtime_forward_headers,
    get_runtime_env,
    get_runtime_float,
)


def _postgres_service_url() -> str:
    return str(get_runtime_env("POSTGRES_SERVICE_URL", "http://127.0.0.1:8008"))


def _lightrag_service_url() -> str:
    return str(get_runtime_env("LIGHTRAG_SERVICE_URL", "http://127.0.0.1:8000"))


def _lightrag_timeout_seconds() -> float:
    return get_runtime_float("LIGHTRAG_TIMEOUT_SECONDS", 120.0)


def _safe_json_loads(body: str) -> dict | list | None:
    if not body.strip():
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"raw_body": body}


def _build_url(base_url: str, path: str, query: dict[str, str] | None = None) -> str:
    url = f"{base_url.rstrip('/')}{path}"
    if query:
        url = f"{url}?{parse.urlencode(query)}"
    return url


def _is_retryable_http_code(status_code: int) -> bool:
    return status_code in {502, 503, 504}


def _is_retryable_url_error(exc: error.URLError) -> bool:
    reason = str(exc.reason).lower()
    return any(
        token in reason
        for token in ("timed out", "timeout", "connection refused", "connection reset", "temporarily unavailable", "no route to host")
    )


def _with_retry(operation, *, max_attempts: int, sleep_seconds: float):
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            payload = (exc.code, _safe_json_loads(body))
            if attempt >= max_attempts or not _is_retryable_http_code(exc.code):
                return payload
            time.sleep(sleep_seconds)
        except error.URLError as exc:
            last_error = exc
            if attempt >= max_attempts or not _is_retryable_url_error(exc):
                raise
            time.sleep(sleep_seconds)
    if last_error is not None:
        raise last_error
    raise RuntimeError("Retry helper exited unexpectedly.")


def postgres_get(path: str, query: dict[str, str] | None = None) -> tuple[int, dict | list | None]:
    url = _build_url(_postgres_service_url(), path, query)
    def _operation():
        req = request.Request(url, headers=build_runtime_forward_headers(), method="GET")
        with request.urlopen(req, timeout=_lightrag_timeout_seconds()) as response:
            body = response.read().decode("utf-8")
            return response.status, _safe_json_loads(body)
    return _with_retry(_operation, max_attempts=2, sleep_seconds=1)


def postgres_post(path: str, payload: dict) -> tuple[int, dict | list | None]:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", **build_runtime_forward_headers()}
    def _operation():
        req = request.Request(
            _build_url(_postgres_service_url(), path),
            data=data,
            headers=headers,
            method="POST",
        )
        with request.urlopen(req, timeout=_lightrag_timeout_seconds()) as response:
            body = response.read().decode("utf-8")
            return response.status, _safe_json_loads(body)
    return _with_retry(_operation, max_attempts=2, sleep_seconds=1)


def postgres_patch(path: str, payload: dict) -> tuple[int, dict | list | None]:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", **build_runtime_forward_headers()}
    def _operation():
        req = request.Request(
            _build_url(_postgres_service_url(), path),
            data=data,
            headers=headers,
            method="PATCH",
        )
        with request.urlopen(req, timeout=_lightrag_timeout_seconds()) as response:
            body = response.read().decode("utf-8")
            return response.status, _safe_json_loads(body)
    return _with_retry(_operation, max_attempts=2, sleep_seconds=1)


def postgres_delete(path: str) -> tuple[int, dict | list | None]:
    def _operation():
        req = request.Request(
            _build_url(_postgres_service_url(), path),
            headers=build_runtime_forward_headers(),
            method="DELETE",
        )
        with request.urlopen(req, timeout=_lightrag_timeout_seconds()) as response:
            body = response.read().decode("utf-8")
            return response.status, _safe_json_loads(body)

    return _with_retry(_operation, max_attempts=2, sleep_seconds=1)


def postgres_create_service_error(payload: dict) -> tuple[int, dict | list | None]:
    return postgres_post("/db/service-errors", payload)


def postgres_patch_service_error(error_id: str, payload: dict) -> tuple[int, dict | list | None]:
    return postgres_patch(f"/db/service-errors/{error_id}", payload)


def lightrag_post(path: str, payload: dict) -> tuple[int, dict | list | None]:
    data = json.dumps(payload).encode("utf-8")
    lightrag_service_url = _lightrag_service_url()
    headers = {"Content-Type": "application/json", **build_runtime_forward_headers()}
    def _operation():
        req = request.Request(
            _build_url(lightrag_service_url, path),
            data=data,
            headers=headers,
            method="POST",
        )
        with request.urlopen(req, timeout=_lightrag_timeout_seconds()) as response:
            body = response.read().decode("utf-8")
            return response.status, _safe_json_loads(body)
    try:
        return _with_retry(_operation, max_attempts=2, sleep_seconds=1)
    except error.URLError as exc:
        raise RuntimeError(
            f"Could not reach LightRAG service at {lightrag_service_url}. "
            f"Make sure the service is running and reachable. Root error: {exc.reason}"
        ) from exc
