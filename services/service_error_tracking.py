"""Shared middleware to record service failures in Postgres."""

from __future__ import annotations

import datetime
import time
import traceback
from typing import Any

import httpx

from services.runtime_config import build_runtime_forward_headers, get_runtime_env


def _postgres_service_url() -> str:
    return str(get_runtime_env("POSTGRES_SERVICE_URL", "http://127.0.0.1:8008"))


def _operation_name(request: Any) -> str:
    return f"{request.method} {request.url.path}"


def _error_context(request: Any, *, exc: Exception | None = None, response_status: int | None = None) -> dict[str, Any]:
    context: dict[str, Any] = {
        "method": getattr(request, "method", None),
        "path": str(getattr(getattr(request, "url", None), "path", "")),
        "service_url": _postgres_service_url(),
        "attempt": 1,
    }
    query_string = getattr(getattr(request, "url", None), "query", None)
    if query_string:
        context["query_string"] = str(query_string)
    if response_status is not None:
        context["status_code"] = response_status
    if exc is not None:
        context["exception_type"] = type(exc).__name__
        context["traceback"] = traceback.format_exc()
    return context


async def _record_service_error(
    *,
    service_name: str,
    operation_name: str,
    status: str,
    error_message: str | None,
    error_context: dict[str, Any],
    duration_ms: int | None,
    headers: Any,
) -> None:
    payload = {
        "service_name": service_name,
        "operation_name": operation_name,
        "status": status,
        "error_message": error_message,
        "error_context": error_context,
        "retry_count": 0,
        "duration_ms": duration_ms,
    }
    async with httpx.AsyncClient(
        base_url=_postgres_service_url(),
        timeout=10.0,
        headers={"Content-Type": "application/json", **build_runtime_forward_headers()},
    ) as client:
        await client.post("/db/service-errors", json=payload, headers=headers)


async def _resolve_latest_service_error(
    *,
    service_name: str,
    operation_name: str,
    headers: Any,
) -> None:
    async with httpx.AsyncClient(
        base_url=_postgres_service_url(),
        timeout=10.0,
        headers={"Content-Type": "application/json", **build_runtime_forward_headers()},
    ) as client:
        for unresolved_status in ("failed", "retrying", "open"):
            response = await client.get(
                "/db/service-errors",
                params={"service_name": service_name, "status": unresolved_status, "limit": 1},
                headers=headers,
            )
            if response.status_code >= 400:
                continue
            items = response.json() if response.content else []
            if not isinstance(items, list) or not items:
                continue
            latest = items[0]
            if not isinstance(latest, dict):
                continue
            if str(latest.get("operation_name") or "") != operation_name:
                continue
            error_id = latest.get("error_id")
            if not isinstance(error_id, str) or not error_id.strip():
                continue
            await client.patch(
                f"/db/service-errors/{error_id}",
                json={
                    "status": "resolved",
                    "resolved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                },
                headers=headers,
            )
            return


def make_service_error_tracking_middleware(service_name: str):
    async def middleware(request, call_next):
        started = time.perf_counter()
        operation_name = _operation_name(request)
        headers = build_runtime_forward_headers()
        path = str(getattr(getattr(request, "url", None), "path", ""))
        skip_tracking = path.startswith("/db/service-errors")
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            if not skip_tracking:
                try:
                    await _record_service_error(
                        service_name=service_name,
                        operation_name=operation_name,
                        status="failed",
                        error_message=str(exc),
                        error_context=_error_context(request, exc=exc),
                        duration_ms=duration_ms,
                        headers=headers,
                    )
                except Exception:
                    pass
            raise

        duration_ms = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            if not skip_tracking:
                try:
                    await _record_service_error(
                        service_name=service_name,
                        operation_name=operation_name,
                        status="failed",
                        error_message=f"HTTP {response.status_code}",
                        error_context=_error_context(request, response_status=response.status_code),
                        duration_ms=duration_ms,
                        headers=headers,
                    )
                except Exception:
                    pass
        else:
            if path in {"/", "/health", "/docs", "/openapi.json", "/redoc", "/api"} or skip_tracking:
                return response
            try:
                await _resolve_latest_service_error(
                    service_name=service_name,
                    operation_name=operation_name,
                    headers=headers,
                )
            except Exception:
                pass

        return response

    return middleware
