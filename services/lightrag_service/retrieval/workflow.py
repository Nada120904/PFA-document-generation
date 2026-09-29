"""Text retrieval workflow using LightRAG (service-local)."""

from __future__ import annotations

import logging
import time

from lightrag import QueryParam

from services.lightrag_service.lightrag_client import activate_lightrag_runtime_env, get_lightrag_client

logger = logging.getLogger(__name__)


async def run_text_retrieval(
    query: str,
    *,
    top_k: int = 2,
    search_type: str = "naive",
    enable_rerank: bool = False,
) -> dict:
    """Execute a text retrieval against LightRAG and return results."""
    total_start = time.perf_counter()
    async with activate_lightrag_runtime_env():
        client = get_lightrag_client()
        init_start = time.perf_counter()
        await client.initialize_storages()
        logger.info(
            "retrieval.step step=initialize_storages elapsed_ms=%s mode=%s top_k=%s",
            int((time.perf_counter() - init_start) * 1000),
            search_type,
            top_k,
        )

        params = QueryParam(
            mode=search_type,
            top_k=top_k,
            chunk_top_k=top_k,
            enable_rerank=enable_rerank,
        )
        query_start = time.perf_counter()
        retrieval_data = await client.aquery_data(query, param=params)
    logger.info(
        "retrieval.step step=lightrag_query elapsed_ms=%s mode=%s top_k=%s",
        int((time.perf_counter() - query_start) * 1000),
        search_type,
        top_k,
    )
    logger.info(
        "retrieval.step step=workflow_total elapsed_ms=%s mode=%s top_k=%s",
        int((time.perf_counter() - total_start) * 1000),
        search_type,
        top_k,
    )
    return {
        "query": query,
        "top_k": top_k,
        "search_type": search_type,
        "retrieval_data": retrieval_data,
    }
