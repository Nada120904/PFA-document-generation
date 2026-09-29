"""Grounded answer generation for the chatbot workflow."""

from __future__ import annotations

import os
from typing import Any
from services.runtime_config import get_runtime_env

ANSWER_SYSTEM_PROMPT = """You are the final response layer for a retrieval-augmented chatbot.

Your job is to answer the user's current message using the structured context provided by the application.

Follow these rules strictly:
- Use the provided context only. Do not invent facts.
- Prefer retrieved document chunks for document-specific factual claims.
- Use long-term memory for stable user preferences, profile facts, and ongoing context.
- Use the session summary and recent messages for continuity inside the current conversation.
- If the retrieved documents are not relevant to the user's question, do not force document-based claims.
- If the answer is partially supported, answer the supported part clearly and state what is missing.
- If the context does not contain enough information to answer, say so plainly and briefly.
- Keep the answer well structured, helpful, and direct.
- Do not mention internal section names like "context_blocks" or "retrieved_chunks".
- Do not mention implementation details such as LangGraph, Qdrant, or middleware unless the user asked about them and the context supports it.
- When the user asks for a preference, project fact, or remembered detail, use long-term memory if it is present.
- When the user asks about uploaded documents, prioritize retrieved document chunks.
- If recent messages conflict with long-term memory, trust the more recent explicit user instruction for this reply.

Answer style:
- Default to concise but complete answers.
- If the user asks for detail, provide a fuller explanation.
- If the user asks a simple fact question, answer it in 1-3 sentences.
- Use bullets only when they improve clarity.
""".strip()


def require_answer_dependencies():
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "Answer generation requires langchain-openai to be installed."
        ) from exc

    return ChatOpenAI


def _runtime_llm_api_key() -> str:
    return (
        str(get_runtime_env("OPENAI_API_KEY", "")).strip()
        or "not-needed"
    )


def _format_context_lines(title: str, items: list[str]) -> str:
    if not items:
        return f"{title}:\n- None"
    rendered = "\n".join(f"- {item}" for item in items)
    return f"{title}:\n{rendered}"


def _format_recent_messages(messages: list[dict[str, str]]) -> str:
    if not messages:
        return "Recent messages:\n- None"
    rendered = "\n".join(
        f"- {message.get('role', 'unknown')}: {message.get('content', '')}"
        for message in messages
    )
    return f"Recent messages:\n{rendered}"


def _build_user_prompt(context: dict[str, object]) -> str:
    user_query = str(context.get("user_query", "")).strip()
    optimized_query = str(context.get("optimized_query", "")).strip() or user_query
    session_summary = str(context.get("session_summary", "")).strip()
    long_term_memory = [
        str(item).strip()
        for item in context.get("long_term_memory", [])
        if str(item).strip()
    ]
    retrieved_chunks = [
        str(item).strip()
        for item in context.get("retrieved_chunks", [])
        if str(item).strip()
    ]
    recent_messages = [
        message
        for message in context.get("recent_messages", [])
        if isinstance(message, dict)
    ]

    sections = [
        f"Current user query:\n{user_query or 'None'}",
        f"Optimized query:\n{optimized_query or 'None'}",
        f"Session summary:\n{session_summary or 'None'}",
        _format_recent_messages(recent_messages),
        _format_context_lines("Long-term memory", long_term_memory),
        _format_context_lines("Retrieved document chunks", retrieved_chunks),
        (
            "Task:\n"
            "Write the best grounded answer to the current user query using the context above."
        ),
    ]
    return "\n\n".join(sections)


def _get_answer_model():
    ChatOpenAI = require_answer_dependencies()
    model_name = (
        str(get_runtime_env("CHATBOT_ANSWER_MODEL", "")).strip()
        or str(get_runtime_env("LLM_MODEL_NAME", "")).strip()
        or "gpt-4o-mini"
    )
    base_url = (
        str(get_runtime_env("CHATBOT_ANSWER_BASE_URL", "")).strip()
        or str(get_runtime_env("OPENAI_BASE_URL", "")).strip()
        or None
    )
    model_kwargs: dict[str, Any] = {
        "model": model_name,
        "temperature": 0,
        "api_key": _runtime_llm_api_key(),
    }
    if base_url:
        model_kwargs["base_url"] = base_url
    return ChatOpenAI(**model_kwargs)


def build_answer_from_context(context: dict[str, object]) -> str:
    user_query = str(context.get("user_query", "")).strip()
    if not user_query:
        return "I do not have a user query to answer."

    model = _get_answer_model()
    user_prompt = _build_user_prompt(context)
    response = model.invoke(
        [
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )
    content = getattr(response, "content", "")
    if isinstance(content, str) and content.strip():
        return content.strip()
    return "I could not generate a grounded answer from the available context."
