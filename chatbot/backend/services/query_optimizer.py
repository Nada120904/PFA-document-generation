"""Query optimization service for the chatbot workflow.

The optimizer is intentionally independent from the retrieval client. It decides
how a user query should be rewritten or expanded, then the workflow decides how
to call LightRAG.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from chatbot.backend.services.service_clients import postgres_post
from services.runtime_config import (
    get_runtime_bool,
    get_runtime_env,
    get_runtime_float,
    get_runtime_int,
)

ROUTE_SIMPLE = "simple"
ROUTE_AMBIGUOUS = "ambiguous"
ROUTE_MULTI_TOPIC = "multi_topic"
ROUTE_COMPLEX = "complex"

logger = logging.getLogger(__name__)

_FOLLOW_UP_MARKERS = {
    "and",
    "also",
    "it",
    "its",
    "they",
    "them",
    "this",
    "that",
    "those",
    "these",
    "he",
    "she",
    "his",
    "her",
    "their",
    "et",
    "aussi",
    "cela",
    "ça",
    "ceci",
    "son",
    "sa",
    "ses",
    "leurs",
    "lui",
    "elle",
    "eux",
}

_COMPLEX_MARKERS = {
    "compare",
    "comparison",
    "evaluate",
    "analyze",
    "analyse",
    "synthesize",
    "synthèse",
    "synthese",
    "recommend",
    "best",
    "better",
    "trade-off",
    "tradeoff",
    "versus",
    "vs",
    "comparer",
    "évaluer",
    "evaluer",
    "analyser",
    "recommande",
    "meilleur",
    "meilleure",
}

_TOPIC_SEPARATORS = re.compile(r"\b(and|or|et|ou|ainsi que)\b|[,;/]")


@dataclass(slots=True)
class QueryOptimizerInput:
    user_message: str
    recent_messages: list[dict[str, str]] = field(default_factory=list)
    session_summary: str | None = None
    long_term_memory: list[str] = field(default_factory=list)
    session_id: str | None = None
    user_id: str | None = None


@dataclass(slots=True)
class QueryOptimizerResult:
    query_run_id: str
    original_query: str
    optimized_query: str
    route_type: str
    strategy: str
    confidence: float
    variants: list[str] = field(default_factory=list)
    sub_questions: list[str] = field(default_factory=list)
    used_llm: bool = False
    llm_model: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def optimize_query(payload: QueryOptimizerInput) -> QueryOptimizerResult:
    query = _normalize_query(payload.user_message)
    if not query:
        return QueryOptimizerResult(
            query_run_id=str(uuid.uuid4()),
            original_query=payload.user_message,
            optimized_query="",
            route_type=ROUTE_SIMPLE,
            strategy="empty_query",
            confidence=1.0,
            reason="No user query text was provided.",
        )

    llm_output = _run_langchain_json_chain(
        task="optimize",
        query=query,
        payload=payload,
        expected_key="route_type",
    )
    if llm_output:
        logger.info("query_optimizer.result_build start task=optimize")
        result = _build_result_from_optimizer_output(
            payload=payload,
            query=query,
            output=llm_output,
        )
        logger.info("query_optimizer.result_build done task=optimize")
        return result

    logger.info("query_optimizer.llm unavailable; defaulting to direct retrieval")
    return QueryOptimizerResult(
        query_run_id=str(uuid.uuid4()),
        original_query=payload.user_message,
        optimized_query=query,
        route_type=ROUTE_SIMPLE,
        strategy="direct_retrieval_without_llm",
        confidence=0.25,
        reason="LLM optimizer unavailable; query was not classified or rewritten.",
    )


def _build_result_from_optimizer_output(
    *,
    payload: QueryOptimizerInput,
    query: str,
    output: dict[str, Any],
) -> QueryOptimizerResult:
    route_type = _normalize_route_type(output.get("route_type"))
    if route_type is None:
        route_type = ROUTE_SIMPLE

    optimized_query = _normalize_query(str(output.get("optimized_query") or query))
    variants = _clean_list(output.get("variants"), fallback=[])
    sub_questions = _clean_list(output.get("sub_questions"), fallback=[])
    reason = str(output.get("reason") or "Single LLM optimizer selected route and retrieval plan.")

    has_context = bool(payload.recent_messages or payload.session_summary or payload.long_term_memory)
    if route_type == ROUTE_SIMPLE:
        strategy = "direct_retrieval"
        variants = []
        sub_questions = []
    elif route_type == ROUTE_AMBIGUOUS:
        variants = []
        sub_questions = []
        if has_context:
            strategy = "history_aware_rewrite"
        else:
            strategy = "ambiguous_no_context"
            optimized_query = query
            reason = (
                "The query is ambiguous, but no chat history, summary, or memory is available for rewrite. "
                f"{reason}"
            )
    elif route_type == ROUTE_MULTI_TOPIC:
        strategy = "llm_multi_query_generation"
        sub_questions = []
        if not variants:
            variants = [optimized_query]
    else:
        strategy = "llm_query_decomposition"
        variants = []
        if not sub_questions:
            sub_questions = [optimized_query]

    confidence = _calculate_confidence(
        route_type=route_type,
        query=query,
        optimized_query=optimized_query,
        variants=variants,
        sub_questions=sub_questions,
        has_context=has_context,
    )

    return QueryOptimizerResult(
        query_run_id=str(uuid.uuid4()),
        original_query=payload.user_message,
        optimized_query=optimized_query,
        route_type=route_type,
        strategy=strategy,
        confidence=confidence,
        variants=variants,
        sub_questions=sub_questions,
        used_llm=True,
        llm_model=_llm_model_name(),
        reason=reason,
    )


def _normalize_route_type(value: Any) -> str | None:
    route = str(value or "").strip().lower()
    route_aliases = {
        "simple": ROUTE_SIMPLE,
        "direct": ROUTE_SIMPLE,
        "ambiguous": ROUTE_AMBIGUOUS,
        "follow_up": ROUTE_AMBIGUOUS,
        "follow-up": ROUTE_AMBIGUOUS,
        "multi_topic": ROUTE_MULTI_TOPIC,
        "multi-topic": ROUTE_MULTI_TOPIC,
        "multi": ROUTE_MULTI_TOPIC,
        "complex": ROUTE_COMPLEX,
    }
    return route_aliases.get(route)


def _calculate_confidence(
    *,
    route_type: str,
    query: str,
    optimized_query: str,
    variants: list[str],
    sub_questions: list[str],
    has_context: bool,
) -> float:
    score = 0.55
    if route_type == ROUTE_SIMPLE:
        score += 0.2 if optimized_query == query else 0.1
    elif route_type == ROUTE_AMBIGUOUS:
        if has_context and optimized_query and optimized_query != query:
            score += 0.3
        elif has_context:
            score += 0.1
        else:
            score -= 0.2
    elif route_type == ROUTE_MULTI_TOPIC:
        if len(variants) >= 2:
            score += 0.3
        elif len(variants) == 1:
            score += 0.1
        else:
            score -= 0.15
    elif route_type == ROUTE_COMPLEX:
        if len(sub_questions) >= 2:
            score += 0.3
        elif len(sub_questions) == 1:
            score += 0.1
        else:
            score -= 0.15
    return round(max(0.0, min(score, 0.95)), 2)


def save_query_optimization_run(
    *,
    result: QueryOptimizerResult,
    session_id: str | None,
    user_id: str | None,
) -> None:
    if not result.original_query.strip():
        return

    try:
        postgres_post(
            "/db/query-optimization-runs",
            {
                "query_run_id": result.query_run_id,
                "session_id": session_id,
                "user_id": user_id,
                "original_query": result.original_query,
                "optimized_query": result.optimized_query,
                "route_type": result.route_type,
                "strategy": result.strategy,
                "confidence": result.confidence,
                "variants": result.variants,
                "sub_questions": result.sub_questions,
                "used_llm": result.used_llm,
                "llm_model": result.llm_model,
                "reason": result.reason,
            },
        )
    except Exception:
        # Query optimization is part of the request path; tracing must not break chat.
        return


def _run_langchain_json_chain(
    *,
    task: str,
    query: str,
    payload: QueryOptimizerInput,
    expected_key: str,
) -> dict[str, Any] | None:
    if not get_runtime_bool("CHATBOT_QUERY_OPTIMIZER_USE_LANGCHAIN", False):
        return _run_openai_json_request(
            task=task,
            query=query,
            payload=payload,
            expected_key=expected_key,
        )

    try:
        from langchain_openai import ChatOpenAI
    except ImportError:
        logger.info("query_optimizer.llm skipped reason=missing_langchain_dependency task=%s", task)
        return None

    model_name = _llm_model_name()
    base_url = get_runtime_env("CHATBOT_QUERY_OPTIMIZER_BASE_URL") or get_runtime_env("OPENAI_BASE_URL")
    timeout_seconds = get_runtime_float("CHATBOT_QUERY_OPTIMIZER_TIMEOUT_SECONDS", 45.0)
    max_retries = get_runtime_int("CHATBOT_QUERY_OPTIMIZER_MAX_RETRIES", 0)
    logger.info(
        "query_optimizer.llm start task=%s model=%s base_url=%s timeout_seconds=%s max_retries=%s",
        task,
        model_name,
        base_url,
        timeout_seconds,
        max_retries,
    )
    model = ChatOpenAI(
        model=model_name,
        api_key=(
            get_runtime_env("CHATBOT_QUERY_OPTIMIZER_API_KEY")
            or get_runtime_env("OPENAI_API_KEY")
            or "not-needed"
        ),
        base_url=base_url,
        temperature=0,
        timeout=timeout_seconds,
        max_retries=max_retries,
    )
    try:
        started_at = time.perf_counter()
        messages = [
            (
                "system",
                (
                    "You optimize retrieval queries for a LightRAG chatbot. "
                    "Return strict JSON only. Do not answer the user question."
                ),
            ),
            (
                "user",
                _prompt_for_task(task).format(
                    query=query,
                    recent_messages=json.dumps(payload.recent_messages[-6:], ensure_ascii=False),
                    session_summary=payload.session_summary or "",
                    long_term_memory=json.dumps(payload.long_term_memory[:8], ensure_ascii=False),
                ),
            ),
        ]
        response = model.invoke(messages)
        content = response.content
        if isinstance(content, list):
            content = "".join(str(part) for part in content)
        result = json.loads(str(content))
        logger.info(
            "query_optimizer.llm done task=%s elapsed_ms=%s",
            task,
            int((time.perf_counter() - started_at) * 1000),
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("query_optimizer.llm invalid_json task=%s error=%s", task, exc)
        return None
    except Exception as exc:
        logger.warning("query_optimizer.llm failed task=%s error=%s", task, exc)
        return None

    if not isinstance(result, dict) or expected_key not in result:
        logger.warning(
            "query_optimizer.llm invalid_output task=%s expected_key=%s output_type=%s",
            task,
            expected_key,
            type(result).__name__,
        )
        return None
    return result


def _run_openai_json_request(
    *,
    task: str,
    query: str,
    payload: QueryOptimizerInput,
    expected_key: str,
) -> dict[str, Any] | None:
    try:
        from openai import OpenAI
    except ImportError:
        logger.info("query_optimizer.llm skipped reason=missing_openai_dependency task=%s", task)
        return None

    model_name = _llm_model_name()
    base_url = get_runtime_env("CHATBOT_QUERY_OPTIMIZER_BASE_URL") or get_runtime_env("OPENAI_BASE_URL")
    timeout_seconds = get_runtime_float("CHATBOT_QUERY_OPTIMIZER_TIMEOUT_SECONDS", 45.0)
    max_retries = get_runtime_int("CHATBOT_QUERY_OPTIMIZER_MAX_RETRIES", 0)
    logger.info(
        "query_optimizer.llm start task=%s backend=openai model=%s base_url=%s timeout_seconds=%s max_retries=%s",
        task,
        model_name,
        base_url,
        timeout_seconds,
        max_retries,
    )
    client = OpenAI(
        api_key=(
            get_runtime_env("CHATBOT_QUERY_OPTIMIZER_API_KEY")
            or get_runtime_env("OPENAI_API_KEY")
            or "not-needed"
        ),
        base_url=base_url,
        timeout=timeout_seconds,
        max_retries=max_retries,
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You optimize retrieval queries for a LightRAG chatbot. "
                "Return strict JSON only. Do not answer the user question."
            ),
        },
        {
            "role": "user",
            "content": _prompt_for_task(task).format(
                query=query,
                recent_messages=json.dumps(payload.recent_messages[-6:], ensure_ascii=False),
                session_summary=payload.session_summary or "",
                long_term_memory=json.dumps(payload.long_term_memory[:8], ensure_ascii=False),
            ),
        },
    ]
    try:
        started_at = time.perf_counter()
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        result = json.loads(content)
        logger.info(
            "query_optimizer.llm done task=%s backend=openai elapsed_ms=%s",
            task,
            int((time.perf_counter() - started_at) * 1000),
        )
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("query_optimizer.llm invalid_json task=%s backend=openai error=%s", task, exc)
        return None
    except Exception as exc:
        logger.warning("query_optimizer.llm failed task=%s backend=openai error=%s", task, exc)
        return None

    if not isinstance(result, dict) or expected_key not in result:
        logger.warning(
            "query_optimizer.llm invalid_output task=%s backend=openai expected_key=%s output_type=%s",
            task,
            expected_key,
            type(result).__name__,
        )
        return None
    return result


def _prompt_for_task(task: str) -> str:
    if task == "optimize":
        return (
            "You are the single query optimizer for a LightRAG chatbot. Your job is to decide how the "
            "retrieval query should be sent to LightRAG. Do not answer the user.\n\n"
            "Input fields:\n"
            "- user query: the latest user message.\n"
            "- recent messages: short chat history, newest messages are most important.\n"
            "- session summary: compact summary of older turns.\n"
            "- long-term memory: optional user memory facts.\n\n"
            "Choose exactly one route_type:\n"
            "- simple: the user query is already clear and standalone. Keep optimized_query close to the original. "
            "variants and sub_questions must be empty.\n"
            "- ambiguous: the query is a follow-up or underspecified. If context exists, rewrite it as one standalone "
            "optimized_query using only the provided context. If no context exists, keep optimized_query equal to the "
            "original query and explain that clarification is needed. variants and sub_questions must be empty.\n"
            "- multi_topic: the query asks for multiple independent topics/aspects where retrieval coverage should be "
            "improved. Keep optimized_query as the overall user intent and generate 2-4 standalone variants. "
            "sub_questions must be empty.\n"
            "- complex: the query requires comparison, evaluation, synthesis, recommendation, or multi-step reasoning. "
            "Keep optimized_query as the overall user intent and generate 2-5 standalone sub_questions that retrieve "
            "evidence for the final answer. variants must be empty.\n\n"
            "Decision examples:\n"
            "- 'What are the benefits of cloud computing?' -> simple.\n"
            "- 'Et ses avantages ?' with previous topic cloud computing -> ambiguous, optimized_query='Quels sont les avantages du cloud computing ?'.\n"
            "- 'Et ses avantages ?' with no context -> ambiguous, optimized_query unchanged, reason asks for clarification.\n"
            "- 'Explain cloud security, cost, and scalability' -> multi_topic with variants for each aspect.\n"
            "- 'Compare two solutions by cost, security, and performance and recommend the best one' -> complex with sub_questions.\n\n"
            "Return strict JSON only with this schema:\n"
            "{{"
            "\"route_type\": \"simple|ambiguous|multi_topic|complex\", "
            "\"optimized_query\": string, "
            "\"variants\": string[], "
            "\"sub_questions\": string[], "
            "\"reason\": string"
            "}}\n\n"
            "User query: {query}\n"
            "Recent messages: {recent_messages}\n"
            "Session summary: {session_summary}\n"
            "Long-term memory: {long_term_memory}"
        )
    raise ValueError(f"Unsupported query optimizer task: {task}")


def _normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


def _clean_list(value: Any, *, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    cleaned: list[str] = []
    for item in value:
        if isinstance(item, dict):
            item = item.get("question") or item.get("query") or item.get("text") or ""
        text = str(item).strip()
        if text:
            cleaned.append(text)
    return _dedupe(cleaned) or fallback


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _llm_model_name() -> str:
    return (
        str(get_runtime_env("CHATBOT_QUERY_OPTIMIZER_MODEL", "")).strip()
        or str(get_runtime_env("LLM_MODEL_NAME", "")).strip()
        or "gpt-4o-mini"
    )
