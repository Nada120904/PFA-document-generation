"""Post-processing for indexed entities (service-local)."""

from __future__ import annotations

import json
import re
import ssl
import urllib.error
import urllib.request
from collections import defaultdict
from typing import Any

from services.lightrag_service.config import get_settings


def _sanitize_model_name(model_name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", model_name).strip("_").lower()
    return value or "model"


def _entity_collection_name() -> str:
    settings = get_settings()
    if settings.qdrant_collection_entities.strip():
        return settings.qdrant_collection_entities.strip()
    model = _sanitize_model_name(settings.embedding_model_name)
    return f"lightrag_vdb_entities_{model}_{settings.embedding_dim}d"


def _normalize_entity_name(name: str) -> str:
    text = name.strip().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    tokens = []
    for token in text.split(" "):
        if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
            tokens.append(token[:-1])
        else:
            tokens.append(token)
    return " ".join(tokens).strip()


def _post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout: int = 60,
    qdrant_api_key: str = "",
    insecure_tls: bool = False,
) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if qdrant_api_key:
        headers["api-key"] = qdrant_api_key
    req = urllib.request.Request(
        url=url,
        data=data,
        headers=headers,
        method="POST",
    )
    ssl_context = None
    if insecure_tls and url.lower().startswith("https://"):
        ssl_context = ssl._create_unverified_context()
    with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body) if body else {}


def _scroll_entities_for_file(
    *,
    qdrant_url: str,
    collection: str,
    file_path: str,
    qdrant_api_key: str = "",
    insecure_tls: bool = False,
) -> list[dict[str, Any]]:
    endpoint = f"{qdrant_url.rstrip('/')}/collections/{collection}/points/scroll"
    points: list[dict[str, Any]] = []
    offset: str | int | None = None

    while True:
        payload: dict[str, Any] = {
            "limit": 256,
            "with_payload": True,
            "with_vector": False,
            "filter": {
                "must": [
                    {"key": "file_path", "match": {"value": file_path}},
                ]
            },
        }
        if offset is not None:
            payload["offset"] = offset

        res = _post_json(
            endpoint,
            payload,
            qdrant_api_key=qdrant_api_key,
            insecure_tls=insecure_tls,
        )
        result = res.get("result") or {}
        batch = result.get("points") or []
        points.extend(batch)

        next_offset = result.get("next_page_offset")
        if not next_offset:
            break
        offset = next_offset

    return points


def _delete_points(
    *,
    qdrant_url: str,
    collection: str,
    point_ids: list[str],
    qdrant_api_key: str = "",
    insecure_tls: bool = False,
) -> None:
    if not point_ids:
        return
    endpoint = f"{qdrant_url.rstrip('/')}/collections/{collection}/points/delete"
    batch_size = 256
    for i in range(0, len(point_ids), batch_size):
        chunk = point_ids[i : i + batch_size]
        _post_json(
            endpoint,
            {"points": chunk, "wait": True},
            qdrant_api_key=qdrant_api_key,
            insecure_tls=insecure_tls,
        )


def dedupe_entities_for_file(*, file_path: str) -> dict[str, Any]:
    """Deduplicate obvious entity variants for one indexed file path in Qdrant."""
    settings = get_settings()
    collection = _entity_collection_name()

    try:
        points = _scroll_entities_for_file(
            qdrant_url=settings.qdrant_url,
            collection=collection,
            file_path=file_path,
            qdrant_api_key=settings.qdrant_api_key,
            insecure_tls=settings.qdrant_insecure_tls,
        )
    except urllib.error.HTTPError as exc:
        return {
            "enabled": True,
            "applied": False,
            "collection": collection,
            "error": f"http_{exc.code}",
        }
    except Exception as exc:  # pragma: no cover
        return {
            "enabled": True,
            "applied": False,
            "collection": collection,
            "error": str(exc),
        }

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for point in points:
        payload = point.get("payload") or {}
        entity_name = str(payload.get("entity_name") or "").strip()
        key = _normalize_entity_name(entity_name)
        if key:
            groups[key].append(point)

    to_delete: list[str] = []
    duplicate_groups = 0
    for _, group_points in groups.items():
        if len(group_points) <= 1:
            continue
        duplicate_groups += 1
        for p in group_points[1:]:
            pid = p.get("id")
            if pid is not None:
                to_delete.append(str(pid))

    _delete_points(
        qdrant_url=settings.qdrant_url,
        collection=collection,
        point_ids=to_delete,
        qdrant_api_key=settings.qdrant_api_key,
        insecure_tls=settings.qdrant_insecure_tls,
    )

    return {
        "enabled": True,
        "applied": True,
        "collection": collection,
        "file_path": file_path,
        "scanned_rows": len(points),
        "duplicate_groups": duplicate_groups,
        "deleted_rows": len(to_delete),
    }
