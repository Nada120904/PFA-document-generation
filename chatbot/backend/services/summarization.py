"""Real middleware-backed conversation summarization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from services.runtime_config import get_runtime_env, get_runtime_int

SESSION_SUMMARY_PROMPT = """You are summarizing one chatbot session so the application can keep long conversations compact without losing important context.

Your job is to produce a clean, compact session summary that will replace older raw messages in the model context.

Rules:
- If an existing session summary appears in the messages, treat it as prior context to refine, not text to repeat.
- Return one updated summary only.
- Write a factual summary of the conversation so far.
- Keep only information that is useful for continuing the same session later.
- Preserve user goals, project context, decisions, constraints, preferences, open questions, and important facts.
- Do not copy the conversation turn by turn.
- Do not repeat information already captured clearly.
- Do not include filler, greetings, or small talk unless they matter.
- Do not mention that you are summarizing.
- Do not start with phrases like "Here is a summary".
- Keep the summary concise but complete enough for the assistant to continue the work correctly.
- If the conversation contains technical work, include concrete items such as architecture choices, file names, services, database decisions, API decisions, unresolved issues, and next steps.
- Ignore placeholder assistant text unless it reveals a real decision or state.

Write the summary in this structure:

Session context:
Main goal, project/task context, and what the user is trying to achieve.

Important decisions:
Architecture, tool, framework, storage, or workflow decisions already made.

Important facts and constraints:
Concrete facts that must be remembered later.

Open items:
Questions, unfinished work, or next steps that still matter.

Messages to summarize:
{messages}
"""


@dataclass(slots=True)
class SummarizationConfig:
    model: str = (
        str(get_runtime_env("CHATBOT_SUMMARY_MODEL", "")).strip()
        or str(get_runtime_env("LLM_MODEL_NAME", "")).strip()
        or "gpt-4o-mini"
    )
    trigger_messages: int = get_runtime_int("CHATBOT_SUMMARY_TRIGGER_MESSAGES", 12)
    trigger_tokens: int = get_runtime_int("CHATBOT_SUMMARY_TRIGGER_TOKENS", 4000)
    keep_messages: int = get_runtime_int("CHATBOT_SUMMARY_KEEP_MESSAGES", 4)
    trim_tokens_to_summarize: int | None = get_runtime_int("CHATBOT_SUMMARY_TRIM_TOKENS", 4000)
    summary_prompt: str = SESSION_SUMMARY_PROMPT


def require_summarization_dependencies() -> None:
    try:
        import langchain  # noqa: F401
        import langchain_openai  # noqa: F401
        import langgraph  # noqa: F401
        import tiktoken  # noqa: F401
    except ImportError as exc:
        raise RuntimeError(
            "Real summarization requires langchain, langchain-openai, langgraph, and tiktoken to be installed."
        ) from exc


def _runtime_llm_api_key() -> str:
    return str(get_runtime_env("OPENAI_API_KEY", "")).strip() or "not-needed"


def get_summarization_middleware(config: SummarizationConfig | None = None):
    require_summarization_dependencies()

    from langchain.agents.middleware import SummarizationMiddleware
    from langchain_openai import ChatOpenAI

    settings = config or SummarizationConfig()
    model_kwargs: dict[str, Any] = {
        "model": settings.model,
        "api_key": _runtime_llm_api_key(),
    }
    base_url = str(get_runtime_env("OPENAI_BASE_URL", "")).strip() or None
    if base_url:
        model_kwargs["base_url"] = base_url
    model = ChatOpenAI(**model_kwargs)
    return SummarizationMiddleware(
        model=model,
        trigger=[
            ("messages", settings.trigger_messages),
            ("tokens", settings.trigger_tokens),
        ],
        keep=("messages", settings.keep_messages),
        token_counter=count_tokens_for_messages,
        summary_prompt=settings.summary_prompt,
        trim_tokens_to_summarize=settings.trim_tokens_to_summarize,
    )


def count_tokens_for_messages(messages: list[Any]) -> int:
    require_summarization_dependencies()

    import tiktoken

    config = SummarizationConfig()
    model_for_token_count = str(get_runtime_env("TIKTOKEN_MODEL_NAME", "")).strip() or config.model
    try:
        encoding = tiktoken.encoding_for_model(model_for_token_count)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    total = 0
    for message in messages:
        if isinstance(message, dict):
            role = str(message.get("role", ""))
            content = str(message.get("content", ""))
        else:
            role = str(getattr(message, "type", ""))
            content = str(getattr(message, "content", ""))

        total += len(encoding.encode(role))
        total += len(encoding.encode(content))
        total += 4

    return total


def should_trigger_summarization(
    *,
    recent_messages: list[dict[str, str]],
    config: SummarizationConfig | None = None,
) -> bool:
    settings = config or SummarizationConfig()
    if len(recent_messages) >= settings.trigger_messages:
        return True
    return count_tokens_for_messages(recent_messages) >= settings.trigger_tokens


def build_messages_for_summary(
    *,
    previous_summary: str | None,
    recent_messages: list[dict[str, str]],
) -> list[dict[str, str]]:
    if not previous_summary or not previous_summary.strip():
        return list(recent_messages)

    return [
        {
            "role": "system",
            "content": (
                "Existing session summary to refine and replace:\n"
                f"{previous_summary.strip()}"
            ),
        },
        *recent_messages,
    ]


def to_langchain_messages(messages: list[dict[str, str]]):
    require_summarization_dependencies()

    from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

    converted = []
    for message in messages:
        role = str(message.get("role", "")).lower()
        content = str(message.get("content", ""))
        if role == "assistant":
            converted.append(AIMessage(content=content))
        elif role == "system":
            converted.append(SystemMessage(content=content))
        elif role == "tool":
            converted.append(ToolMessage(content=content, tool_call_id="chatbot-tool"))
        else:
            converted.append(HumanMessage(content=content))
    return converted


def from_langchain_message(message: Any) -> dict[str, str]:
    message_type = getattr(message, "type", "human")
    role_map = {
        "human": "user",
        "ai": "assistant",
        "system": "system",
        "tool": "tool",
    }
    return {
        "role": role_map.get(message_type, "user"),
        "content": str(getattr(message, "content", "")),
    }


def clean_summary_text(summary_text: str, previous_summary: str | None = None) -> str:
    cleaned = summary_text.strip()
    prefixes_to_strip = [
        "Here is a summary of the conversation to date:",
        "Here is a summary of the conversation so far:",
        "Here is the summary of the conversation to date:",
        "Here is the updated summary of the conversation:",
    ]
    for prefix in prefixes_to_strip:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :].strip()
    if previous_summary and cleaned == previous_summary.strip():
        return previous_summary.strip()
    return cleaned


def apply_summarization_policy(
    *,
    previous_summary: str | None,
    recent_messages: list[dict[str, str]],
    config: SummarizationConfig | None = None,
) -> dict[str, object]:
    if not should_trigger_summarization(recent_messages=recent_messages, config=config):
        return {
            "summary_text": previous_summary,
            "recent_messages": recent_messages,
            "summary_updated": False,
            "middleware_available": True,
        }

    middleware = get_summarization_middleware(config)
    messages_for_summary = build_messages_for_summary(
        previous_summary=previous_summary,
        recent_messages=recent_messages,
    )
    langchain_messages = to_langchain_messages(messages_for_summary)

    updates = middleware.before_model({"messages": langchain_messages}, None)
    if not updates or "messages" not in updates:
        return {
            "summary_text": previous_summary,
            "recent_messages": recent_messages,
            "summary_updated": False,
            "middleware_available": True,
        }

    updated_messages = list(updates["messages"])
    filtered_messages = [
        message
        for message in updated_messages
        if message.__class__.__name__ != "RemoveMessage"
    ]

    if not filtered_messages:
        return {
            "summary_text": previous_summary,
            "recent_messages": recent_messages,
            "summary_updated": False,
            "middleware_available": True,
        }

    summary_message = filtered_messages[0]
    kept_messages = []
    for message in filtered_messages[1:]:
        content = str(getattr(message, "content", ""))
        if content.startswith("Existing session summary to refine and replace:\n"):
            continue
        kept_messages.append(message)

    summary_text = clean_summary_text(
        str(getattr(summary_message, "content", "")),
        previous_summary=previous_summary,
    )

    return {
        "summary_text": summary_text,
        "recent_messages": [from_langchain_message(message) for message in kept_messages],
        "summary_updated": True,
        "middleware_available": True,
    }
