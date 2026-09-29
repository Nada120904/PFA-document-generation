"""Request analysis service for the document generation workflow.

Decides whether a user message is a normal chat query or a document
generation request, and if generation, extracts the requested format
and any parameters already present in the message.
"""

from __future__ import annotations

import json
import logging
import re

from services.runtime_config import get_runtime_env, get_runtime_float

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You classify user messages for a document-generation assistant.\n\n"
    "You will be given the recent conversation history (if any) followed by the "
    "latest user message. Use the FULL conversation to accumulate information — "
    "if earlier turns mentioned a title, language, style, etc., carry those "
    "forward even if the latest message doesn't repeat them.\n\n"
    "Decide if the CURRENT request (considering context) is:\n"
    "- \"chat\": a normal question or conversation\n"
    "- \"generation\": a request to generate/create a file (PDF, DOCX, CSV, or TXT), "
    "including a reply that is answering a previous question about generation parameters\n\n"
    "If \"generation\", also extract into params any of these fields the user has "
    "specified so far, across the whole conversation (only include fields relevant "
    "to the detected format):\n"
    "- topic: what the document should be about\n"
    "- title: document title\n"
    "- language: document language (e.g. English, French)\n"
    "- style: writing style/tone (e.g. formal, casual, technical)\n"
    "- layout: layout preference (PDF)\n"
    "- pages: number of pages, integer (PDF)\n"
    "- headings: list or description of section headings (DOCX)\n"
    "- sections: description of report sections (DOCX)\n"
    "- structure: structure preference (DOCX/TXT)\n"
    "- rows: number of rows, integer (CSV)\n"
    "- columns: column names, list or description (CSV)\n"
    "- header: whether to include a header row, true/false (CSV)\n"
    "- delimiter: field delimiter, e.g. comma, semicolon (CSV)\n"
    "- data_type: what kind of data to generate (CSV)\n"
    "- length: desired length, e.g. short/medium/long or word count (TXT)\n\n"
    "Return strict JSON only, with this exact schema:\n"
    "{\"type\": \"chat\" or \"generation\", \"format\": string or null, \"params\": {}}\n\n"
    "Only include keys in params that the user has actually specified. Do not guess "
    "or invent values.\n\n"
    "Examples:\n"
    "\"What is machine learning?\" -> {\"type\": \"chat\", \"format\": null, \"params\": {}}\n"
    "\"Generate a 2-page PDF report about AI in healthcare\" -> "
    "{\"type\": \"generation\", \"format\": \"pdf\", \"params\": {\"pages\": 2, \"topic\": \"AI in healthcare\"}}\n"
)

REQUIRED_PARAMS_BY_FORMAT = {
    "pdf": [], "docx": [], "csv": [], "txt": [],
}

# Kept for backward compatibility with existing imports
REQUIRED_PDF_PARAMS = REQUIRED_PARAMS_BY_FORMAT["pdf"]
_FALLBACK_RESULT = {"type": "chat", "format": None, "params": {}}


def analyze_request(user_message: str, recent_messages: list | None = None) -> dict:
    """Classify a user message as chat or document generation, using conversation history."""
    query = user_message.strip()
    if not query:
        return dict(_FALLBACK_RESULT)

    # Explicit export requests should work even without an LLM or API key.
    format_match = re.search(r"\b(pdf|docx|csv|txt)\b", query, re.IGNORECASE)
    action_match = re.search(r"\b(generate|create|make|write|export|download)\b", query, re.IGNORECASE)
    if format_match and action_match:
        topic_match = re.search(r"\b(?:about|on)\s+(.+?)(?:[.!?]|$)", query, re.IGNORECASE)
        params = {"topic": topic_match.group(1).strip()} if topic_match else {}
        return {"type": "generation", "format": format_match.group(1).lower(), "params": params}

    result = _run_openai_json_request(query, recent_messages or [])
    if result is None:
        logger.warning("request_analyzer.llm_unavailable defaulting_to_chat")
        return dict(_FALLBACK_RESULT)

    return {
        "type": result.get("type") if result.get("type") in {"chat", "generation"} else "chat",
        "format": result.get("format") if result.get("format") in {"pdf", "docx", "csv", "txt"} else None,
        "params": result.get("params") if isinstance(result.get("params"), dict) else {},
    }


def _run_openai_json_request(query: str, recent_messages: list) -> dict | None:
    try:
        from openai import OpenAI
    except ImportError:
        logger.info("request_analyzer.llm skipped reason=missing_openai_dependency")
        return None

    model_name = str(get_runtime_env("LLM_MODEL_NAME", "")).strip() or "gpt-4o-mini"
    base_url = get_runtime_env("OPENAI_BASE_URL")
    timeout_seconds = get_runtime_float("CHATBOT_QUERY_OPTIMIZER_TIMEOUT_SECONDS", 45.0)

    client = OpenAI(
        api_key=get_runtime_env("OPENAI_API_KEY") or "not-needed",
        base_url=base_url,
        timeout=timeout_seconds,
    )

    history_lines = []
    for msg in recent_messages[-8:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if content:
            history_lines.append(f"{role}: {content}")
    history_text = "\n".join(history_lines)

    user_content = (
        f"Conversation so far:\n{history_text}\n\nLatest message:\n{query}"
        if history_text
        else query
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        result = json.loads(content)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("request_analyzer.llm invalid_json error=%s", exc)
        return None
    except Exception as exc:
        logger.warning("request_analyzer.llm failed error=%s", exc)
        return None

    if not isinstance(result, dict) or "type" not in result:
        logger.warning("request_analyzer.llm invalid_output output_type=%s", type(result).__name__)
        return None
    return result
