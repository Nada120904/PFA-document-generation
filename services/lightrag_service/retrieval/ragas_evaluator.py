"""RAGAS evaluation helpers for retrieval service."""

from __future__ import annotations

from typing import Any

from services.lightrag_service.config import get_settings


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        value = getattr(value, "value")
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def evaluate_retrieval_with_ragas(
    *,
    question: str,
    retrieved_contexts: list[str],
    reference: str | None,
    response: str | None = None,
) -> dict[str, Any]:
    base_scores = {
        "context_precision": None,
        "context_recall": None,
        "f1_context": None,
        "context_relevance": None,
        "answer_accuracy": None,
        "answer_relevancy": None,
    }

    if not retrieved_contexts:
        return {
            "available": False,
            "reason": "No retrieved contexts to evaluate.",
            "scores": base_scores,
            "errors": {"global": "No retrieved contexts to evaluate."},
        }

    try:
        from openai import AsyncOpenAI
        from ragas.embeddings import embedding_factory
        from ragas.llms import llm_factory
        from ragas.metrics.collections import (
            AnswerAccuracy,
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            ContextRelevance,
        )
    except Exception as exc:
        return {
            "available": False,
            "reason": f"RAGAS import failed: {exc}",
            "scores": base_scores,
            "errors": {"global": f"RAGAS import failed: {exc}"},
        }

    try:
        settings = get_settings()
        client_kwargs: dict[str, Any] = {}
        if settings.openai_api_key:
            client_kwargs["api_key"] = settings.openai_api_key
        if settings.openai_base_url:
            client_kwargs["base_url"] = settings.openai_base_url

        client = AsyncOpenAI(**client_kwargs)
        llm_model_name = settings.ragas_llm_model_name or settings.llm_model_name
        embedding_model_name = (
            settings.ragas_embedding_model_name or settings.embedding_model_name
        )

        llm = llm_factory(llm_model_name, client=client)
        embeddings = embedding_factory(
            "openai",
            model=embedding_model_name,
            client=client,
            interface="modern",
        )

        scores = dict(base_scores)
        errors: dict[str, str] = {}

        try:
            context_relevance_scorer = ContextRelevance(llm=llm)
            context_relevance_result = await context_relevance_scorer.ascore(
                user_input=question,
                retrieved_contexts=retrieved_contexts,
            )
            scores["context_relevance"] = _to_float_or_none(context_relevance_result)
        except Exception as exc:
            errors["context_relevance"] = str(exc)

        if reference is not None and reference.strip():
            try:
                precision_scorer = ContextPrecision(llm=llm)
                precision_result = await precision_scorer.ascore(
                    user_input=question,
                    reference=reference,
                    retrieved_contexts=retrieved_contexts,
                )
                scores["context_precision"] = _to_float_or_none(precision_result)
            except Exception as exc:
                errors["context_precision"] = str(exc)

            try:
                recall_scorer = ContextRecall(llm=llm)
                recall_result = await recall_scorer.ascore(
                    user_input=question,
                    reference=reference,
                    retrieved_contexts=retrieved_contexts,
                )
                scores["context_recall"] = _to_float_or_none(recall_result)
            except Exception as exc:
                errors["context_recall"] = str(exc)
        else:
            errors["reference"] = "No reference provided for context_precision/context_recall."

        precision = scores.get("context_precision")
        recall = scores.get("context_recall")
        if isinstance(precision, float) and isinstance(recall, float) and (precision + recall) > 0:
            scores["f1_context"] = (2 * precision * recall) / (precision + recall)

        if response is not None and response.strip():
            try:
                answer_relevancy_scorer = AnswerRelevancy(llm=llm, embeddings=embeddings)
                answer_relevancy_result = await answer_relevancy_scorer.ascore(
                    user_input=question,
                    response=response,
                )
                scores["answer_relevancy"] = _to_float_or_none(answer_relevancy_result)
            except Exception as exc:
                errors["answer_relevancy"] = str(exc)

            if reference is not None and reference.strip():
                try:
                    answer_accuracy_scorer = AnswerAccuracy(llm=llm)
                    answer_accuracy_result = await answer_accuracy_scorer.ascore(
                        user_input=question,
                        response=response,
                        reference=reference,
                    )
                    scores["answer_accuracy"] = _to_float_or_none(answer_accuracy_result)
                except Exception as exc:
                    errors["answer_accuracy"] = str(exc)
            else:
                errors["answer_accuracy"] = "No reference provided for answer_accuracy."
        else:
            errors["response"] = "No response provided for answer-level metrics."

        return {
            "available": True if any(v is not None for v in scores.values()) else False,
            "reason": None if any(v is not None for v in scores.values()) else "RAGAS scoring returned no metric values.",
            "scores": scores,
            "errors": errors,
        }
    except Exception as exc:
        return {
            "available": False,
            "reason": f"RAGAS execution failed: {exc}",
            "scores": base_scores,
            "errors": {"global": f"RAGAS execution failed: {exc}"},
        }
