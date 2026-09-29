"""Fallback content generation when retrieval finds nothing indexed."""

from __future__ import annotations

import logging

from services.runtime_config import get_runtime_env, get_runtime_float

logger = logging.getLogger(__name__)


def generate_fallback_content(topic: str, language: str, style: str) -> list[str]:
    try:
        from openai import OpenAI
    except ImportError:
        return ["No indexed content was found, and the fallback generator is unavailable."]

    model_name = str(get_runtime_env("LLM_MODEL_NAME", "")).strip() or "gpt-4o-mini"
    base_url = get_runtime_env("OPENAI_BASE_URL")
    timeout_seconds = get_runtime_float("CHATBOT_QUERY_OPTIMIZER_TIMEOUT_SECONDS", 45.0)

    client = OpenAI(
        api_key=get_runtime_env("OPENAI_API_KEY") or "not-needed",
        base_url=base_url,
        timeout=timeout_seconds,
    )

    prompt = (
        f"Write informative content in {language or 'English'}, {style or 'neutral'} style, "
        f"about: {topic}. Structure it as 3 to 5 short paragraphs suitable for a PDF report. "
        "Return ONLY the paragraphs, separated by a blank line, no headings, no markdown."
    )

    try:
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
        )
        text = response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("content_generator.fallback_failed error=%s", exc)
        return [f"Content generation failed: {exc}"]

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return paragraphs or [text.strip()]