from __future__ import annotations

import asyncio
import math
import os
import json
import re
from pathlib import Path
from urllib.parse import urlparse, urlsplit, urlunsplit
import logging
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar

import httpx

from services.lightrag_service.config import get_settings

logger = logging.getLogger(__name__)
_LIGHTRAG_RUNTIME_LOCK = asyncio.Lock()
_HF_RERANKERS: dict[str, tuple[object, object, object]] = {}
_DOCUMENT_METADATA_CONTEXT: ContextVar[dict[str, object] | None] = ContextVar(
    "lightrag_document_metadata_context",
    default=None,
)
_RETRIEVAL_METADATA_FILTERS_CONTEXT: ContextVar[dict[str, list[str]] | None] = ContextVar(
    "lightrag_retrieval_metadata_filters_context",
    default=None,
)
_RETRIEVAL_ALLOWED_DOCUMENTS_CONTEXT: ContextVar[dict[str, list[str]] | None] = ContextVar(
    "lightrag_retrieval_allowed_documents_context",
    default=None,
)


@contextmanager
def _temporary_environ(updates: dict[str, str], removals: set[str] | None = None):
    removals = removals or set()
    original: dict[str, str | None] = {}
    touched = set(updates) | removals
    for key in touched:
        original[key] = os.environ.get(key)

    try:
        for key in removals:
            os.environ.pop(key, None)
        for key, value in updates.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _normalize_metadata_key(key: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", str(key).strip().lower()).strip("_")
    return normalized or "metadata"


def _build_flat_metadata_payload(metadata: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(metadata, dict):
        return {}

    flat_payload: dict[str, object] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        normalized_key = _normalize_metadata_key(str(key))
        flat_payload[f"metadata__{normalized_key}"] = str(value)
    return flat_payload


@contextmanager
def use_lightrag_document_metadata(
    *,
    document_id: str,
    file_path: str,
    metadata: dict[str, object] | None,
):
    token = _DOCUMENT_METADATA_CONTEXT.set(
        {
            "document_id": document_id,
            "file_path": file_path,
            "metadata": metadata if isinstance(metadata, dict) else {},
        }
    )
    try:
        yield
    finally:
        _DOCUMENT_METADATA_CONTEXT.reset(token)


@contextmanager
def use_lightrag_retrieval_metadata_filters(filters: dict[str, list[str]] | None):
    normalized_filters: dict[str, list[str]] = {}
    if isinstance(filters, dict):
        for key, values in filters.items():
            cleaned_values = [str(value).strip() for value in values if str(value).strip()]
            if cleaned_values:
                normalized_filters[str(key)] = cleaned_values

    token = _RETRIEVAL_METADATA_FILTERS_CONTEXT.set(normalized_filters or None)
    try:
        yield
    finally:
        _RETRIEVAL_METADATA_FILTERS_CONTEXT.reset(token)


@contextmanager
def use_lightrag_retrieval_allowed_documents(
    *,
    document_ids: list[str] | None = None,
    file_paths: list[str] | None = None,
):
    cleaned_document_ids = [str(value).strip() for value in (document_ids or []) if str(value).strip()]
    cleaned_file_paths = [str(value).strip() for value in (file_paths or []) if str(value).strip()]
    payload = {
        "document_ids": cleaned_document_ids,
        "file_paths": cleaned_file_paths,
    }
    token = _RETRIEVAL_ALLOWED_DOCUMENTS_CONTEXT.set(payload)
    try:
        yield
    finally:
        _RETRIEVAL_ALLOWED_DOCUMENTS_CONTEXT.reset(token)


def _build_qdrant_metadata_filter(models_module) -> object | None:
    filters = _RETRIEVAL_METADATA_FILTERS_CONTEXT.get()
    if not filters:
        return None

    should_conditions: list[object] = []
    for key, values in filters.items():
        key_conditions = [
            models_module.FieldCondition(
                key=f"metadata__{_normalize_metadata_key(key)}",
                match=models_module.MatchValue(value=str(value)),
            )
            for value in values
            if str(value).strip()
        ]
        if not key_conditions:
            continue
        should_conditions.extend(key_conditions)

    if not should_conditions:
        return None
    return models_module.Filter(must=[models_module.Filter(should=should_conditions)])


def _build_qdrant_allowed_documents_filter(models_module) -> object | None:
    allowed_documents = _RETRIEVAL_ALLOWED_DOCUMENTS_CONTEXT.get()
    if not allowed_documents:
        return None

    should_conditions: list[object] = []
    for document_id in allowed_documents.get("document_ids", []):
        if str(document_id).strip():
            should_conditions.append(
                models_module.FieldCondition(
                    key="document_id",
                    match=models_module.MatchValue(value=str(document_id)),
                )
            )

    for file_path in allowed_documents.get("file_paths", []):
        if str(file_path).strip():
            should_conditions.append(
                models_module.FieldCondition(
                    key="file_path",
                    match=models_module.MatchValue(value=str(file_path)),
                )
            )

    if not should_conditions:
        return None
    return models_module.Filter(must=[models_module.Filter(should=should_conditions)])


async def sync_document_metadata_to_neo4j(
    *,
    client: object,
    document_id: str,
    file_path: str,
    metadata: dict[str, object] | None,
) -> None:
    graph = getattr(client, "chunk_entity_relation_graph", None)
    driver = getattr(graph, "_driver", None)
    database = getattr(graph, "_DATABASE", None)
    workspace_label_getter = getattr(graph, "_get_workspace_label", None)
    if driver is None or not callable(workspace_label_getter):
        return

    workspace_label = workspace_label_getter()
    metadata_dict = metadata if isinstance(metadata, dict) else {}
    metadata_items = [
        {"key": str(key), "value": str(value)}
        for key, value in metadata_dict.items()
        if value is not None and str(key).strip() and str(value).strip()
    ]
    metadata_json = json.dumps(metadata_dict, ensure_ascii=False) if metadata_dict else None

    async with driver.session(database=database) as session:
        result = await session.run(
            f"""
            MERGE (d:`{workspace_label}`:Document {{document_id: $document_id}})
            SET d.file_path = $file_path,
                d.metadata_json = $metadata_json,
                d.updated_at = datetime()
            """,
            document_id=document_id,
            file_path=file_path,
            metadata_json=metadata_json,
        )
        await result.consume()
        result = await session.run(
            f"""
            MATCH (d:`{workspace_label}`:Document {{document_id: $document_id}})-[r:HAS_METADATA]->(:Metadata)
            DELETE r
            """,
            document_id=document_id,
        )
        await result.consume()
        if metadata_items:
            result = await session.run(
                f"""
                MATCH (d:`{workspace_label}`:Document {{document_id: $document_id}})
                UNWIND $items AS item
                MERGE (m:`{workspace_label}`:Metadata {{key: item.key, value: item.value}})
                MERGE (d)-[:HAS_METADATA]->(m)
                """,
                document_id=document_id,
                items=metadata_items,
            )
            await result.consume()

    logger.info(
        "LightRAG Neo4j metadata sync done: document_id=%s metadata_keys=%s",
        document_id,
        [item["key"] for item in metadata_items],
    )


def _apply_qdrant_collection_overrides() -> None:
    """Override LightRAG Qdrant collection names via env-configured mapping."""
    from lightrag.kg.qdrant_impl import QdrantVectorDBStorage
    from lightrag.utils import logger

    if getattr(QdrantVectorDBStorage, "_custom_collection_override_applied", False):
        return

    original_post_init = QdrantVectorDBStorage.__post_init__

    def _patched_post_init(self):  # type: ignore[no-untyped-def]
        original_post_init(self)
        settings = get_settings()
        mapping = {
            "entities": settings.qdrant_collection_entities.strip(),
            "relationships": settings.qdrant_collection_relationships.strip(),
            "chunks": settings.qdrant_collection_chunks.strip(),
        }
        override_name = mapping.get(getattr(self, "namespace", ""))
        if override_name:
            self.final_namespace = override_name
            logger.info(
                f"[{self.workspace}] Qdrant collection override: namespace={self.namespace} -> {self.final_namespace}"
            )

    QdrantVectorDBStorage.__post_init__ = _patched_post_init
    setattr(QdrantVectorDBStorage, "_custom_collection_override_applied", True)


def _apply_qdrant_client_runtime_overrides() -> None:
    """
    Patch LightRAG's internal Qdrant client construction:
    - avoid gRPC fallback for remote HTTPS endpoints
    - allow insecure TLS mode when explicitly requested
    """
    from lightrag.kg import qdrant_impl as qdrant_impl_module

    if getattr(qdrant_impl_module, "_custom_qdrant_client_override_applied", False):
        return

    original_qdrant_client = qdrant_impl_module.QdrantClient

    def _patched_qdrant_client(*args, **kwargs):  # type: ignore[no-untyped-def]
        settings = get_settings()
        collection_to_vector_name: dict[str, str] = {}
        if settings.qdrant_collection_entities.strip() and settings.qdrant_vector_name_entities.strip():
            collection_to_vector_name[settings.qdrant_collection_entities.strip()] = (
                settings.qdrant_vector_name_entities.strip()
            )
        if settings.qdrant_collection_relationships.strip() and settings.qdrant_vector_name_relationships.strip():
            collection_to_vector_name[settings.qdrant_collection_relationships.strip()] = (
                settings.qdrant_vector_name_relationships.strip()
            )
        if settings.qdrant_collection_chunks.strip() and settings.qdrant_vector_name_chunks.strip():
            collection_to_vector_name[settings.qdrant_collection_chunks.strip()] = (
                settings.qdrant_vector_name_chunks.strip()
            )
        kwargs.setdefault("prefer_grpc", False)
        if settings.qdrant_insecure_tls:
            kwargs.setdefault("verify", False)
        client = original_qdrant_client(*args, **kwargs)

        if not collection_to_vector_name:
            return client

        from qdrant_client import models  # type: ignore
        from lightrag.utils import logger

        original_upsert = client.upsert
        original_query_points = client.query_points

        def _patched_upsert(*u_args, **u_kwargs):  # type: ignore[no-untyped-def]
            collection_name = u_kwargs.get("collection_name")
            if collection_name is None and len(u_args) >= 1:
                collection_name = u_args[0]
            vector_name = (
                collection_to_vector_name.get(str(collection_name))
                if collection_name is not None
                else None
            )

            points = u_kwargs.get("points")
            if points is None and len(u_args) >= 2:
                points = u_args[1]
            if isinstance(points, list):
                for point in points:
                    if isinstance(point, models.PointStruct):
                        vector = point.vector
                        if vector_name and vector is not None and not isinstance(vector, dict):
                            point.vector = {vector_name: vector}
                        document_context = _DOCUMENT_METADATA_CONTEXT.get()
                        if isinstance(document_context, dict):
                            payload = dict(point.payload or {})
                            payload.setdefault(
                                "document_id",
                                str(document_context.get("document_id", "")).strip(),
                            )
                            payload.setdefault(
                                "file_path",
                                str(document_context.get("file_path", "")).strip(),
                            )
                            metadata = document_context.get("metadata")
                            if isinstance(metadata, dict) and metadata:
                                payload["metadata"] = {
                                    str(key): str(value)
                                    for key, value in metadata.items()
                                    if value is not None and str(key).strip() and str(value).strip()
                                }
                                payload.update(_build_flat_metadata_payload(payload["metadata"]))
                            point.payload = payload

            return original_upsert(*u_args, **u_kwargs)

        def _patched_query_points(*q_args, **q_kwargs):  # type: ignore[no-untyped-def]
            collection_name = q_kwargs.get("collection_name")
            if collection_name is None and len(q_args) >= 1:
                collection_name = q_args[0]
            vector_name = (
                collection_to_vector_name.get(str(collection_name))
                if collection_name is not None
                else None
            )
            if vector_name and "using" not in q_kwargs:
                q_kwargs["using"] = vector_name
            merged_filter = q_kwargs.get("query_filter")
            allowed_documents_filter = _build_qdrant_allowed_documents_filter(models)
            metadata_filter = _build_qdrant_metadata_filter(models)

            for extra_filter in (allowed_documents_filter, metadata_filter):
                if extra_filter is None:
                    continue
                if merged_filter is None:
                    merged_filter = extra_filter
                    continue
                if isinstance(merged_filter, models.Filter):
                    merged_must = list(merged_filter.must or [])
                    merged_should = list(merged_filter.should or [])
                    merged_must_not = list(merged_filter.must_not or [])
                    merged_must.extend(list(extra_filter.must or []))
                    merged_should.extend(list(extra_filter.should or []))
                    merged_must_not.extend(list(extra_filter.must_not or []))
                    merged_filter = models.Filter(
                        must=merged_must,
                        should=merged_should,
                        must_not=merged_must_not,
                    )

            if merged_filter is not None:
                q_kwargs["query_filter"] = merged_filter
            return original_query_points(*q_args, **q_kwargs)

        client.upsert = _patched_upsert  # type: ignore[method-assign]
        client.query_points = _patched_query_points  # type: ignore[method-assign]
        logger.info(
            f"Qdrant named-vector runtime mapping enabled: {collection_to_vector_name}"
        )
        return client

    qdrant_impl_module.QdrantClient = _patched_qdrant_client
    setattr(qdrant_impl_module, "_custom_qdrant_client_override_applied", True)


def _apply_qdrant_legacy_lookup_patch() -> None:
    """
    With scoped tokens (T1/T2/T3), probing unauthorized legacy collections
    raises 403. Skip forbidden candidates and continue.
    """
    from lightrag.kg import qdrant_impl as qdrant_impl_module
    from lightrag.utils import logger
    from qdrant_client.http.exceptions import UnexpectedResponse

    if getattr(qdrant_impl_module, "_custom_legacy_lookup_patch_applied", False):
        return

    def _patched_find_legacy_collection(
        client,
        namespace: str,
        workspace: str = None,
        model_suffix: str = None,
    ):
        candidates = [
            f"lightrag_vdb_{namespace}" if model_suffix else None,
            f"{workspace}_{namespace}" if workspace else None,
            f"lightrag_vdb_{namespace}",
            namespace,
        ]
        for candidate in candidates:
            if not candidate:
                continue
            try:
                if client.collection_exists(candidate):
                    logger.info(
                        f"Qdrant: Found legacy collection '{candidate}' "
                        f"(namespace={namespace}, workspace={workspace or 'none'})"
                    )
                    return candidate
            except UnexpectedResponse as exc:
                text = str(exc)
                if "Forbidden" in text or "Access to collection" in text:
                    logger.info(
                        f"Qdrant: Skip unauthorized legacy collection probe '{candidate}'"
                    )
                    continue
                raise
        return None

    qdrant_impl_module._find_legacy_collection = _patched_find_legacy_collection
    setattr(qdrant_impl_module, "_custom_legacy_lookup_patch_applied", True)


def _build_no_proxy_updates(qdrant_url: str) -> dict[str, str]:
    parsed = urlparse(qdrant_url)
    host = parsed.hostname
    if not host:
        return {}

    updates: dict[str, str] = {}
    for key in ("NO_PROXY", "no_proxy"):
        existing = os.environ.get(key, "")
        values = [v.strip() for v in existing.split(",") if v.strip()]
        for must_have in ("localhost", "127.0.0.1", host):
            if must_have not in values:
                values.append(must_have)
        updates[key] = ",".join(values)
    return updates


def _normalize_qdrant_url(url: str) -> str:
    """
    qdrant-client may fallback to non-HTTP default ports if URL has no explicit port.
    Force standard port for http/https when missing.
    """
    split = urlsplit(url)
    if not split.scheme or not split.hostname or split.port is not None:
        return url

    default_port = None
    if split.scheme == "https":
        default_port = 443
    elif split.scheme == "http":
        default_port = 80
    if default_port is None:
        return url

    auth = ""
    if split.username:
        auth = split.username
        if split.password:
            auth += f":{split.password}"
        auth += "@"
    netloc = f"{auth}{split.hostname}:{default_port}"
    return urlunsplit((split.scheme, netloc, split.path, split.query, split.fragment))


def _embedding_dim_for_model(model_name: str, default_dim: int) -> int:
    name = model_name.strip()
    if name == "text-embedding-3-small":
        return 1536
    if name == "text-embedding-3-large":
        return 3072
    return default_dim


def _apply_lightrag_rerank_score_preservation_patch() -> None:
    """Preserve LightRAG rerank_score in aquery_data raw chunks.

    LightRAG's convert_to_user_format currently formats chunks with a fixed
    subset of fields and drops rerank_score. Keep the package untouched and patch
    the imported function used by lightrag.operate so native rerank scores remain
    visible in retrieval_data.
    """
    from lightrag import operate as operate_module
    from lightrag import utils as utils_module

    if getattr(operate_module, "_custom_rerank_score_preservation_applied", False):
        return

    original_convert = operate_module.convert_to_user_format

    def _patched_convert_to_user_format(
        entities_context,
        relations_context,
        chunks,
        references,
        query_mode,
        entity_id_to_original=None,
        relation_id_to_original=None,
    ):
        formatted = original_convert(
            entities_context,
            relations_context,
            chunks,
            references,
            query_mode,
            entity_id_to_original,
            relation_id_to_original,
        )

        score_by_chunk_id: dict[str, float] = {}
        score_by_position: dict[int, float] = {}
        for index, chunk in enumerate(chunks or []):
            if not isinstance(chunk, dict):
                continue
            score = chunk.get("rerank_score")
            if not isinstance(score, (int, float)):
                continue
            chunk_id = chunk.get("chunk_id")
            if isinstance(chunk_id, str) and chunk_id:
                score_by_chunk_id[chunk_id] = float(score)
            score_by_position[index] = float(score)

        formatted_chunks = formatted.get("data", {}).get("chunks", [])
        if isinstance(formatted_chunks, list):
            for index, chunk in enumerate(formatted_chunks):
                if not isinstance(chunk, dict):
                    continue
                chunk_id = chunk.get("chunk_id")
                score = (
                    score_by_chunk_id.get(chunk_id)
                    if isinstance(chunk_id, str)
                    else None
                )
                if score is None:
                    score = score_by_position.get(index)
                if score is not None:
                    chunk["rerank_score"] = score

        return formatted

    operate_module.convert_to_user_format = _patched_convert_to_user_format
    utils_module.convert_to_user_format = _patched_convert_to_user_format
    setattr(operate_module, "_custom_rerank_score_preservation_applied", True)
    logger.info("LightRAG raw_data rerank_score preservation patch enabled.")


def _sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1 / (1 + z)
    z = math.exp(value)
    return z / (1 + z)


def _get_huggingface_reranker(model_name: str):
    if model_name in _HF_RERANKERS:
        return _HF_RERANKERS[model_name]

    import time
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    load_start = time.perf_counter()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(model_name)
    model.to(device)
    model.eval()
    _HF_RERANKERS[model_name] = (tokenizer, model, device)
    logger.info(
        "Hugging Face reranker loaded: model=%s device=%s elapsed_ms=%s",
        model_name,
        device,
        int((time.perf_counter() - load_start) * 1000),
    )
    return _HF_RERANKERS[model_name]


def _run_huggingface_rerank_sync(
    *,
    query: str,
    documents: list[str],
    top_n: int | None,
    model_name: str,
    batch_size: int,
) -> list[dict[str, float | int]]:
    import time
    import torch

    rerank_start = time.perf_counter()
    tokenizer, model, device = _get_huggingface_reranker(model_name)
    scores: list[tuple[int, float]] = []
    pairs = [(query, document) for document in documents]

    with torch.inference_mode():
        for start in range(0, len(pairs), batch_size):
            batch_pairs = pairs[start : start + batch_size]
            inputs = tokenizer(
                batch_pairs,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            inputs = {key: value.to(device) for key, value in inputs.items()}
            logits = model(**inputs).logits
            if logits.ndim == 2 and logits.shape[1] > 1:
                batch_scores = torch.softmax(logits, dim=1)[:, -1].detach().cpu().tolist()
            else:
                batch_scores = [_sigmoid(float(value)) for value in logits.reshape(-1).detach().cpu().tolist()]
            scores.extend(
                (start + offset, float(score))
                for offset, score in enumerate(batch_scores)
            )

    scores.sort(key=lambda item: item[1], reverse=True)
    if top_n is not None:
        scores = scores[:top_n]
    logger.info(
        "retrieval.step step=huggingface_rerank_sync elapsed_ms=%s documents=%s batch_size=%s top_n=%s device=%s",
        int((time.perf_counter() - rerank_start) * 1000),
        len(documents),
        batch_size,
        top_n,
        device,
    )
    return [
        {"index": index, "relevance_score": score}
        for index, score in scores
    ]


async def call_huggingface_rerank(
    *,
    query: str,
    documents: list[str],
    top_n: int | None,
    model: str,
    batch_size: int,
) -> list[dict[str, float | int]]:
    if not documents:
        return []
    return await asyncio.to_thread(
        _run_huggingface_rerank_sync,
        query=query,
        documents=documents,
        top_n=top_n,
        model_name=model,
        batch_size=max(1, batch_size),
    )


async def call_rerank(
    *,
    query: str,
    documents: list[str],
    top_n: int | None,
    settings,
) -> list[dict[str, float | int]]:
    binding = settings.rerank_binding.strip().lower()
    if binding in {"huggingface", "hf", "local"}:
        return await call_huggingface_rerank(
            query=query,
            documents=documents,
            top_n=top_n,
            model=settings.rerank_model_name.strip() or "cross-encoder/ms-marco-MiniLM-L-6-v2",
            batch_size=settings.rerank_batch_size,
        )
    raise RuntimeError(
        f"Unsupported RERANK_BINDING={settings.rerank_binding!r}. "
        "Supported values: 'huggingface', 'hf', and 'local'."
    )


def _build_rerank_model_func(settings):
    binding = settings.rerank_binding.strip().lower()
    if not binding:
        logger.info("LightRAG native reranker disabled: RERANK_BINDING is empty.")
        return None

    if binding not in {"huggingface", "hf", "local"}:
        raise RuntimeError(
            f"Unsupported RERANK_BINDING={settings.rerank_binding!r}. "
            "Supported values: 'huggingface', 'hf', and 'local'."
        )

    logger.info(
        "LightRAG native reranker enabled: binding=%s model=%s min_score=%s",
        binding,
        settings.rerank_model_name,
        settings.min_rerank_score,
    )

    async def rerank_model_func(query: str, documents: list[str], top_n: int | None = None):
        return await call_rerank(
            query=query,
            documents=documents,
            top_n=top_n,
            settings=settings,
        )

    return rerank_model_func


def _build_openai_client_configs(settings):
    if not settings.openai_insecure_tls:
        return None

    logger.warning(
        "OpenAI TLS verification is disabled for LightRAG. Use only for local/dev "
        "environments until the enterprise CA certificate is configured."
    )
    return {"http_client": httpx.AsyncClient(verify=False)}


@asynccontextmanager
async def activate_lightrag_runtime_env():
    settings = get_settings()
    qdrant_url = _normalize_qdrant_url(settings.qdrant_url.strip())
    env_updates = {
        "QDRANT_URL": qdrant_url,
        "NEO4J_URI": settings.neo4j_url,
        "NEO4J_USERNAME": settings.neo4j_user,
        "NEO4J_PASSWORD": settings.neo4j_password,
        "EMBEDDING_TIMEOUT": str(settings.embedding_timeout),
        "EMBEDDING_FUNC_MAX_ASYNC": str(settings.embedding_func_max_async),
        "LLM_TIMEOUT": str(settings.llm_timeout),
        "LLM_MODEL_MAX_ASYNC": str(settings.llm_model_max_async),
        "MAX_ASYNC": str(settings.llm_model_max_async),
        "QDRANT_UPSERT_MAX_PAYLOAD_BYTES": str(settings.qdrant_upsert_max_payload_bytes),
        "QDRANT_UPSERT_MAX_POINTS_PER_BATCH": str(settings.qdrant_upsert_max_points_per_batch),
    }
    env_removals: set[str] = set()
    if settings.qdrant_api_key:
        env_updates["QDRANT_API_KEY"] = settings.qdrant_api_key
    else:
        env_removals.add("QDRANT_API_KEY")
    if settings.openai_api_key:
        env_updates["OPENAI_API_KEY"] = settings.openai_api_key
    else:
        env_removals.add("OPENAI_API_KEY")
    if settings.openai_base_url:
        env_updates["OPENAI_BASE_URL"] = settings.openai_base_url
        env_updates["OPENAI_API_BASE"] = settings.openai_base_url
    else:
        env_removals.update({"OPENAI_BASE_URL", "OPENAI_API_BASE"})

    env_updates.update(_build_no_proxy_updates(qdrant_url))
    await _LIGHTRAG_RUNTIME_LOCK.acquire()
    try:
        with _temporary_environ(env_updates, env_removals):
            yield
    finally:
        _LIGHTRAG_RUNTIME_LOCK.release()


def get_lightrag_client():
    settings = get_settings()

    working_dir = Path(settings.lightrag_working_dir)
    working_dir.mkdir(parents=True, exist_ok=True)

    try:
        from lightrag import LightRAG
        from lightrag.llm.openai import openai_complete_if_cache, openai_embed
        from lightrag.utils import wrap_embedding_func_with_attrs
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "LightRAG dependencies are not ready. Install lightrag/openai deps first."
        ) from exc

    _apply_qdrant_collection_overrides()
    _apply_qdrant_client_runtime_overrides()
    _apply_qdrant_legacy_lookup_patch()
    _apply_lightrag_rerank_score_preservation_patch()

    embedding_dim = _embedding_dim_for_model(
        settings.embedding_model_name,
        settings.embedding_dim,
    )
    embedding_model_name = settings.embedding_model_name
    rerank_model_func = _build_rerank_model_func(settings)

    @wrap_embedding_func_with_attrs(
        embedding_dim=embedding_dim,
        max_token_size=8192,
        model_name=embedding_model_name,
        send_dimensions=False,
    )
    async def embedding_func(texts: list[str], **kwargs):  # type: ignore[no-untyped-def]
        return await openai_embed.func(
            texts=texts,
            model=embedding_model_name,
            client_configs=_build_openai_client_configs(settings),
            **kwargs,
        )

    async def llm_model_func(
        prompt,
        system_prompt=None,
        history_messages=None,
        keyword_extraction=False,
        **kwargs,
    ):
        if history_messages is None:
            history_messages = []
        model_name = kwargs["hashing_kv"].global_config["llm_model_name"]
        return await openai_complete_if_cache(
            model_name,
            prompt,
            system_prompt=system_prompt,
            history_messages=history_messages,
            keyword_extraction=keyword_extraction,
            base_url=settings.openai_base_url,
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout,
            **kwargs,
        )

    client = LightRAG(
        working_dir=str(working_dir),
        vector_storage="QdrantVectorDBStorage",
        graph_storage="Neo4JStorage",
        chunk_token_size=settings.lightrag_chunk_size,
        chunk_overlap_token_size=settings.lightrag_chunk_overlap_size,
        llm_model_name=settings.llm_model_name,
        llm_model_func=llm_model_func,
        llm_model_max_async=settings.llm_model_max_async,
        default_llm_timeout=settings.llm_timeout,
        tiktoken_model_name=settings.tiktoken_model_name,
        embedding_func=embedding_func,
        embedding_func_max_async=settings.embedding_func_max_async,
        default_embedding_timeout=settings.embedding_timeout,
        rerank_model_func=rerank_model_func,
        min_rerank_score=settings.min_rerank_score,
    )

    return client
