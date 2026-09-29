"""Shared state for the chatbot LangGraph workflow."""

from __future__ import annotations

from typing import TypedDict


class ChatWorkflowState(TypedDict, total=False):
    user_id: str
    session_id: str
    user_message: str
    retrieval_filters: dict[str, list[str]]
    optimized_query: str
    query_optimization: dict[str, object]
    query_route_type: str
    query_variants: list[str]
    query_sub_questions: list[str]
    recent_messages: list[dict[str, str]]
    session_summary: str | None
    long_term_memory: list[str]
    retrieved_chunks: list[dict[str, object]]
    context: dict[str, object]
    answer: str
    memory_candidate: list[dict[str, object]] | None
    request_analysis: dict[str, object]
    request_type: str
    requested_format: str | None
    request_params: dict[str, object]
