"""Long-term memory service backed by LangMem, Qdrant, and Postgres."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from pydantic import BaseModel, Field

from chatbot.backend.services.service_clients import postgres_get, postgres_patch, postgres_post
from services.runtime_config import get_runtime_env, get_runtime_int

logger = logging.getLogger(__name__)

MEMORY_EXTRACTION_INSTRUCTIONS = """
Extract only durable information that is likely to be useful in future conversations.

Store memories when they capture stable or recurring context such as:
- preferences
- goals
- constraints
- project or work context
- personal profile facts
- recurring instructions
- important decisions
- relationships between people, tools, or concepts

Do not store:
- greetings
- small talk
- one-off temporary requests
- information that is useful only for the current single turn
- facts already obvious from the immediate raw message history

For each memory:
- `memory_type` should be a short snake_case label
- `content` should be a concise standalone statement

If the new conversation contradicts or supersedes an existing memory, update or delete the old
memory instead of creating duplicates.
""".strip()


class DurableMemory(BaseModel):
    """A durable memory worth keeping across sessions."""

    memory_type: str = Field(
        description="Short snake_case category like preference, constraint, project_context, goal.",
    )
    content: str = Field(
        description="Concise standalone memory that may help in future conversations.",
    )


@dataclass(frozen=True)
class MemorySettings:
    memory_model: str
    embedding_model: str
    api_key: str
    openai_base_url: str | None
    qdrant_url: str
    qdrant_collection: str
    qdrant_api_key: str | None
    top_k: int
    existing_limit: int
    embedding_dimensions_override: int | None

    @classmethod
    def from_env(cls) -> MemorySettings:
        return cls(
            memory_model=(
                str(get_runtime_env("CHATBOT_MEMORY_LLM_MODEL", "")).strip()
                or str(get_runtime_env("CHATBOT_MEMORY_MODEL", "")).strip()
                or str(get_runtime_env("LLM_MODEL_NAME", "")).strip()
                or "gpt-4o-mini"
            ),
            embedding_model=(
                str(get_runtime_env("CHATBOT_MEMORY_EMBEDDING_MODEL", "")).strip()
                or str(get_runtime_env("EMBEDDING_MODEL_NAME", "")).strip()
                or str(get_runtime_env("OPENAI_EMBEDDING_MODEL", "")).strip()
                or "text-embedding-3-small"
            ),
            api_key=(
                str(get_runtime_env("CHATBOT_MEMORY_API_KEY", "")).strip()
                or str(get_runtime_env("OPENAI_API_KEY", "")).strip()
                or "not-needed"
            ),
            openai_base_url=(
                str(get_runtime_env("CHATBOT_MEMORY_BASE_URL", "")).strip()
                or str(get_runtime_env("OPENAI_BASE_URL", "")).strip()
                or None
            ),
            qdrant_url=str(get_runtime_env("QDRANT_URL", "")).strip(),
            qdrant_collection=str(get_runtime_env("QDRANT_COLLECTION", "")).strip(),
            qdrant_api_key=str(get_runtime_env("QDRANT_API_KEY", "")).strip() or None,
            top_k=max(1, get_runtime_int("CHATBOT_MEMORY_TOP_K", 5)),
            existing_limit=max(1, get_runtime_int("CHATBOT_MEMORY_EXISTING_LIMIT", 8)),
            embedding_dimensions_override=(
                int(
                    str(get_runtime_env("CHATBOT_MEMORY_EMBEDDING_DIM", "")).strip()
                    or str(get_runtime_env("EMBEDDING_DIM", "")).strip()
                )
                if (
                    str(get_runtime_env("CHATBOT_MEMORY_EMBEDDING_DIM", "")).strip()
                    or str(get_runtime_env("EMBEDDING_DIM", "")).strip()
                )
                else None
            ),
        )

    @property
    def embedding_dimensions(self) -> int:
        if self.embedding_dimensions_override is not None:
            return self.embedding_dimensions_override
        if self.embedding_model == "text-embedding-3-large":
            return 3072
        return 1536


@dataclass(frozen=True)
class MemorySearchHit:
    memory_id: str
    user_id: str
    memory_type: str
    content: str
    session_id: str | None
    score: float | None


def _safe_json_loads(body: str) -> dict[str, Any] | list[Any] | None:
    if not body.strip():
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {"raw_body": body}


def get_memory_settings() -> MemorySettings:
    settings = MemorySettings.from_env()
    if not settings.qdrant_url:
        raise RuntimeError("QDRANT_URL is required for long-term memory.")
    if not settings.qdrant_collection:
        raise RuntimeError("QDRANT_COLLECTION is required for long-term memory.")
    return settings


def require_memory_dependencies():
    try:
        from langchain_openai import ChatOpenAI
        from langmem import create_memory_manager
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "Long-term memory dependencies are missing. Install chatbot/backend/requirements.txt."
        ) from exc
    return ChatOpenAI, OpenAI, create_memory_manager


def get_memory_extractor():
    ChatOpenAI, _, create_memory_manager = require_memory_dependencies()
    settings = get_memory_settings()
    model_kwargs: dict[str, Any] = {
        "model": settings.memory_model,
        "temperature": 0,
        "api_key": settings.api_key,
    }
    if settings.openai_base_url:
        model_kwargs["base_url"] = settings.openai_base_url
    model = ChatOpenAI(**model_kwargs)
    return create_memory_manager(
        model,
        schemas=[DurableMemory],
        instructions=MEMORY_EXTRACTION_INSTRUCTIONS,
        enable_inserts=True,
        enable_updates=True,
        enable_deletes=True,
    )


def get_openai_client():
    _, OpenAI, _ = require_memory_dependencies()
    settings = get_memory_settings()
    client_kwargs: dict[str, Any] = {
        "api_key": settings.api_key,
    }
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    return OpenAI(**client_kwargs)


def should_extract_memory(user_message: str) -> bool:
    text = " ".join(user_message.strip().lower().split())
    if not text:
        return False

    explicit_memory_markers = (
        "remember",
        "my name is",
        "i am ",
        "i'm ",
        "i prefer",
        "i like",
        "i love",
        "i dislike",
        "i hate",
        "my favorite",
        "my favourite",
        "for me",
        "i usually",
        "i always",
        "i never",
        "i work on",
        "i'm working on",
        "my project",
        "my team",
        "my goal",
        "my constraint",
        "i need",
        "we need",
    )
    if any(marker in text for marker in explicit_memory_markers):
        return True

    question_starters = (
        "what ",
        "how ",
        "why ",
        "when ",
        "where ",
        "who ",
        "which ",
        "explain ",
        "compare ",
        "summarize ",
        "tell me ",
    )
    if text.endswith("?") or text.startswith(question_starters):
        return False

    return False


def _qdrant_headers() -> dict[str, str]:
    settings = get_memory_settings()
    headers = {"Content-Type": "application/json"}
    if settings.qdrant_api_key:
        headers["api-key"] = settings.qdrant_api_key
    return headers


def _qdrant_request(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, Any] | list[Any] | None]:
    settings = get_memory_settings()
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = request.Request(
        f"{settings.qdrant_url.rstrip('/')}{path}",
        data=data,
        headers=_qdrant_headers(),
        method=method,
    )
    try:
        with request.urlopen(req, timeout=20) as response:
            body = response.read().decode("utf-8")
            return response.status, _safe_json_loads(body)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        return exc.code, _safe_json_loads(body)
    except error.URLError as exc:
        raise RuntimeError("Failed to reach Qdrant for long-term memory operations.") from exc


def _raise_qdrant_error(message: str, *, status_code: int, payload: Any) -> None:
    logger.error("qdrant.error message=%s status=%s payload=%r", message, status_code, payload)
    raise RuntimeError(f"{message} (status={status_code}, payload={payload!r})")


def ensure_qdrant_collection() -> None:
    settings = get_memory_settings()
    status_code, _ = _qdrant_request("GET", f"/collections/{settings.qdrant_collection}")
    if status_code == 200:
        return
    if status_code != 404:
        _raise_qdrant_error(
            "Failed to inspect the Qdrant collection for long-term memory",
            status_code=status_code,
            payload=None,
        )

    status_code, payload = _qdrant_request(
        "PUT",
        f"/collections/{settings.qdrant_collection}",
        {
            "vectors": {
                "size": settings.embedding_dimensions,
                "distance": "Cosine",
            }
        },
    )
    if status_code >= 400:
        _raise_qdrant_error(
            "Failed to create the Qdrant collection for long-term memory",
            status_code=status_code,
            payload=payload,
        )


def embed_text(text: str) -> list[float]:
    cleaned = text.strip()
    if not cleaned:
        raise RuntimeError("Cannot embed empty text for long-term memory.")

    settings = get_memory_settings()
    client = get_openai_client()
    response = client.embeddings.create(
        model=settings.embedding_model,
        input=cleaned,
    )
    return list(response.data[0].embedding)


def _search_qdrant(*, user_id: str, query: str, limit: int) -> list[MemorySearchHit]:
    if not user_id or not query.strip():
        return []

    ensure_qdrant_collection()
    settings = get_memory_settings()
    vector = embed_text(query)
    status_code, payload = _qdrant_request(
        "POST",
        f"/collections/{settings.qdrant_collection}/points/search",
        {
            "vector": vector,
            "limit": limit,
            "with_payload": True,
            "filter": {
                "must": [
                    {"key": "user_id", "match": {"value": user_id}},
                    {"key": "is_active", "match": {"value": True}},
                ]
            },
        },
    )
    if status_code >= 400 or not isinstance(payload, dict):
        _raise_qdrant_error(
            "Failed to search Qdrant for long-term memory",
            status_code=status_code,
            payload=payload,
        )

    results = payload.get("result", [])
    if not isinstance(results, list):
        return []

    hits: list[MemorySearchHit] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        memory_id = str(item.get("id", "")).strip()
        payload_data = item.get("payload", {})
        if not memory_id or not isinstance(payload_data, dict):
            continue
        content = str(payload_data.get("content", "")).strip()
        if not content:
            continue
        hits.append(
            MemorySearchHit(
                memory_id=memory_id,
                user_id=str(payload_data.get("user_id", "")).strip(),
                memory_type=str(payload_data.get("memory_type", "memory")).strip() or "memory",
                content=content,
                session_id=str(payload_data.get("session_id", "")).strip() or None,
                score=float(item["score"]) if item.get("score") is not None else None,
            )
        )
    return hits


def _get_qdrant_payload(memory_id: str) -> dict[str, Any] | None:
    settings = get_memory_settings()
    status_code, payload = _qdrant_request(
        "POST",
        f"/collections/{settings.qdrant_collection}/points",
        {
            "ids": [memory_id],
            "with_payload": True,
            "with_vector": False,
        },
    )
    if status_code >= 400 or not isinstance(payload, dict):
        return None
    result = payload.get("result", [])
    if not isinstance(result, list) or not result:
        return None
    first = result[0]
    if not isinstance(first, dict):
        return None
    point_payload = first.get("payload", {})
    return point_payload if isinstance(point_payload, dict) else None


def _upsert_qdrant_memory(
    *,
    memory_id: str,
    user_id: str,
    session_id: str | None,
    memory_type: str,
    content: str,
) -> None:
    settings = get_memory_settings()
    vector = embed_text(content)
    status_code, payload = _qdrant_request(
        "PUT",
        f"/collections/{settings.qdrant_collection}/points?wait=true",
        {
            "points": [
                {
                    "id": memory_id,
                    "vector": vector,
                    "payload": {
                        "memory_id": memory_id,
                        "user_id": user_id,
                        "session_id": session_id,
                        "memory_type": memory_type,
                        "content": content,
                        "is_active": True,
                    },
                }
            ]
        },
    )
    if status_code >= 400:
        _raise_qdrant_error(
            "Failed to upsert long-term memory in Qdrant",
            status_code=status_code,
            payload=payload,
        )


def _delete_qdrant_memory(memory_id: str) -> None:
    settings = get_memory_settings()
    status_code, payload = _qdrant_request(
        "POST",
        f"/collections/{settings.qdrant_collection}/points/delete?wait=true",
        {"points": [memory_id]},
    )
    if status_code >= 400:
        _raise_qdrant_error(
            "Failed to delete long-term memory from Qdrant",
            status_code=status_code,
            payload=payload,
        )


def _read_memory_record(memory_id: str) -> dict[str, Any] | None:
    status_code, payload = postgres_get(f"/db/memory-records/{memory_id}")
    if status_code == 404 or not isinstance(payload, dict):
        return None
    if status_code >= 400:
        raise RuntimeError("Failed to read memory record from postgres service.")
    return payload


def _ensure_memory_record(
    *,
    memory_id: str,
    user_id: str,
    session_id: str | None,
    memory_type: str,
    confidence: float | None = None,
) -> tuple[dict[str, Any], bool]:
    existing = _read_memory_record(memory_id)
    if existing is None:
        status_code, payload = postgres_post(
            "/db/memory-records",
            {
                "memory_id": memory_id,
                "user_id": user_id,
                "session_id": session_id,
                "source_message_id": None,
                "memory_type": memory_type,
                "confidence": confidence,
                "is_active": True,
            },
        )
        if status_code >= 400 or not isinstance(payload, dict):
            raise RuntimeError("Failed to create memory record in postgres service.")
        return payload, True

    status_code, payload = postgres_patch(
        f"/db/memory-records/{memory_id}",
        {
            "memory_type": memory_type,
            "confidence": confidence,
            "is_active": True,
        },
    )
    if status_code >= 400 or not isinstance(payload, dict):
        raise RuntimeError("Failed to update memory record in postgres service.")
    return payload, False


def _ensure_memory_embedding(memory_id: str) -> None:
    status_code, payload = postgres_get(f"/db/memory-records/{memory_id}/embedding")
    if status_code == 404:
        settings = get_memory_settings()
        status_code, created = postgres_post(
            "/db/memory-embeddings",
            {
                "embedding_id": str(uuid.uuid4()),
                "memory_id": memory_id,
                "qdrant_point_id": memory_id,
                "embedding_model": settings.embedding_model,
            },
        )
        if status_code >= 400 or not isinstance(created, dict):
            raise RuntimeError("Failed to create memory embedding link in postgres service.")
        return
    if status_code >= 400 or not isinstance(payload, dict):
        raise RuntimeError("Failed to read memory embedding link from postgres service.")


def _create_memory_event(
    *,
    memory_id: str,
    event_type: str,
    old_value: str | None,
    new_value: str | None,
    reason: str | None,
) -> None:
    status_code, _ = postgres_post(
        "/db/memory-events",
        {
            "event_id": str(uuid.uuid4()),
            "memory_id": memory_id,
            "event_type": event_type,
            "old_value": old_value,
            "new_value": new_value,
            "reason": reason,
        },
    )
    if status_code >= 400:
        raise RuntimeError("Failed to create memory event in postgres service.")


def _normalize_memory_type(value: str) -> str:
    normalized = "_".join(value.strip().lower().split())
    return normalized or "memory"


def _build_existing_memories(*, user_id: str, query: str) -> list[tuple[str, DurableMemory]]:
    hits = _search_qdrant(
        user_id=user_id,
        query=query,
        limit=get_memory_settings().existing_limit,
    )
    return [
        (
            hit.memory_id,
            DurableMemory(
                memory_type=hit.memory_type,
                content=hit.content,
            ),
        )
        for hit in hits
    ]


def _build_memory_messages(
    *,
    recent_messages: list[dict[str, str]] | None,
    user_message: str,
    assistant_answer: str,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for item in (recent_messages or [])[-6:]:
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()
        if role and content:
            messages.append({"role": role, "content": content})
    if user_message.strip():
        messages.append({"role": "user", "content": user_message.strip()})
    if assistant_answer.strip():
        messages.append({"role": "assistant", "content": assistant_answer.strip()})
    return messages


def _is_remove_doc(content: Any) -> bool:
    return hasattr(content, "json_doc_id") or content.__class__.__name__ == "RemoveDoc"


def _extract_remove_doc_id(content: Any) -> str:
    return str(getattr(content, "json_doc_id", "")).strip()


def _normalize_extracted_memory(item: Any) -> dict[str, Any] | None:
    content = getattr(item, "content", None)
    extracted_id = str(getattr(item, "id", "")).strip() or str(uuid.uuid4())
    if content is None:
        return None

    if _is_remove_doc(content):
        memory_id = _extract_remove_doc_id(content)
        if not memory_id:
            return None
        return {
            "action": "delete",
            "memory_id": memory_id,
        }

    if isinstance(content, DurableMemory):
        data = content.model_dump()
    elif hasattr(content, "model_dump"):
        data = content.model_dump()
    elif isinstance(content, dict):
        data = content
    else:
        return None

    memory_type = _normalize_memory_type(str(data.get("memory_type", "memory")))
    memory_text = str(data.get("content", "")).strip()
    if not memory_text:
        return None

    return {
        "action": "upsert",
        "memory_id": extracted_id,
        "memory_type": memory_type,
        "content": memory_text,
    }


def load_relevant_memory(*, user_id: str, query: str) -> list[str]:
    if not user_id or not query.strip():
        return []

    hits = _search_qdrant(
        user_id=user_id,
        query=query,
        limit=get_memory_settings().top_k,
    )

    memories: list[str] = []
    for hit in hits:
        record = _read_memory_record(hit.memory_id)
        if record is None or not bool(record.get("is_active", True)):
            continue
        memory_type = _normalize_memory_type(str(record.get("memory_type", hit.memory_type)))
        memories.append(f"{memory_type}: {hit.content}")
    if memories:
        logger.warning(
            "memory.retrieve user_id=%s query=%r hits=%s memories=%r",
            user_id,
            query,
            len(memories),
            memories,
        )
    else:
        logger.info(
            "memory.retrieve user_id=%s query=%r hits=%s memories=%r",
            user_id,
            query,
            len(memories),
            memories,
        )
    return memories


def build_memory_candidate(
    *,
    user_id: str,
    session_id: str | None,
    recent_messages: list[dict[str, str]] | None,
    user_message: str,
    assistant_answer: str,
) -> list[dict[str, Any]] | None:
    if not should_extract_memory(user_message):
        return None

    conversation = _build_memory_messages(
        recent_messages=recent_messages,
        user_message=user_message,
        assistant_answer=assistant_answer,
    )
    if not conversation:
        return None

    extractor = get_memory_extractor()
    existing = _build_existing_memories(user_id=user_id, query=user_message)
    extracted_items = extractor.invoke(
        {
            "messages": conversation,
            "existing": existing,
        }
    )

    updates: list[dict[str, Any]] = []
    for item in extracted_items:
        normalized = _normalize_extracted_memory(item)
        if normalized is None:
            continue

        if normalized["action"] == "delete":
            memory_id = str(normalized["memory_id"])
            existing_record = _read_memory_record(memory_id)
            if existing_record is None:
                continue
            old_payload = _get_qdrant_payload(memory_id)
            _delete_qdrant_memory(memory_id)
            status_code, payload = postgres_patch(
                f"/db/memory-records/{memory_id}",
                {
                    "is_active": False,
                },
            )
            if status_code >= 400 or not isinstance(payload, dict):
                raise RuntimeError("Failed to deactivate memory record in postgres service.")
            _create_memory_event(
                memory_id=memory_id,
                event_type="delete",
                old_value=str((old_payload or {}).get("content", "")).strip() or None,
                new_value=None,
                reason="LangMem marked the memory as outdated or contradicted.",
            )
            updates.append(
                {
                    "action": "delete",
                    "memory_id": memory_id,
                }
            )
            continue

        memory_id = str(normalized["memory_id"])
        memory_type = str(normalized["memory_type"])
        memory_text = str(normalized["content"])
        previous_payload = _get_qdrant_payload(memory_id)

        record, created = _ensure_memory_record(
            memory_id=memory_id,
            user_id=user_id,
            session_id=session_id,
            memory_type=memory_type,
        )
        _upsert_qdrant_memory(
            memory_id=memory_id,
            user_id=user_id,
            session_id=session_id,
            memory_type=memory_type,
            content=memory_text,
        )
        _ensure_memory_embedding(memory_id)
        _create_memory_event(
            memory_id=memory_id,
            event_type="insert" if created else "update",
            old_value=str((previous_payload or {}).get("content", "")).strip() or None,
            new_value=memory_text,
            reason="LangMem extracted durable long-term memory from the conversation.",
        )
        updates.append(
            {
                "action": "insert" if created else "update",
                "memory_id": memory_id,
                "memory_type": str(record.get("memory_type", memory_type)),
                "content": memory_text,
            }
        )

    return updates or None
