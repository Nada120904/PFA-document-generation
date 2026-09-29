"""LangGraph workflow scaffold for the chatbot."""

from __future__ import annotations

import logging
import re
from chatbot.backend.services.request_analyzer import analyze_request, REQUIRED_PARAMS_BY_FORMAT
from chatbot.backend.services.txt_generator import generate_txt
from chatbot.backend.services.docx_generator import generate_docx
from chatbot.backend.services.csv_generator import generate_csv

from chatbot.backend.services.pdf_generator import generate_pdf

from chatbot.backend.graph.state import ChatWorkflowState
from chatbot.backend.services.answer_generator import build_answer_from_context
from chatbot.backend.services.context_manager import build_context
from chatbot.backend.services.memory_manager import build_memory_candidate, load_relevant_memory
from chatbot.backend.services.query_optimizer import (
    QueryOptimizerInput,
    optimize_query,
    save_query_optimization_run,
)
from chatbot.backend.services.retrieval_service import retrieve_document_context
from chatbot.backend.services.session_manager import (
    load_or_create_session,
    load_recent_messages,
    load_session_summary_record,
    save_session_summary,
)
from chatbot.backend.services.summarization import apply_summarization_policy

logger = logging.getLogger(__name__)


def load_session_node(state: ChatWorkflowState) -> ChatWorkflowState:
    session = load_or_create_session(
        user_id=state.get("user_id", ""),
        session_id=state.get("session_id"),
        first_message=state.get("user_message", ""),
    )
    session_id = str(session["session_id"])
    recent_messages = load_recent_messages(session_id=session_id)
    summary_record = load_session_summary_record(session_id=session_id)
    session_summary = str(summary_record.get("summary_text")) if summary_record else None
    return {
        **state,
        "session_id": session_id,
        "recent_messages": recent_messages,
        "session_summary": session_summary,
        "session_summary_record": summary_record,
    }

def analyze_request_node(state: ChatWorkflowState) -> ChatWorkflowState:
    analysis = analyze_request(
        state.get("user_message", ""),
        recent_messages=state.get("recent_messages", []),
    )
    return {
        **state,
        "request_analysis": analysis,
        "request_type": analysis.get("type", "chat"),
        "requested_format": analysis.get("format"),
        "request_params": analysis.get("params", {}),
    }


SUPPORTED_FORMATS = {"pdf", "txt", "docx", "csv"}
GENERATION_GENERIC_TERMS = {
    "a", "an", "the", "about", "on", "of", "from", "to", "with", "using", "only",
    "please", "generate", "create", "make", "write", "export", "download",
    "pdf", "docx", "word", "csv", "txt", "summary", "summarize", "report",
    "note", "notes", "document", "documents", "file", "files", "upload", "uploaded",
    "index", "indexed", "data", "content", "source", "sources",
}


def _generation_topic_terms(topic: str) -> set[str]:
    """Keep explicit subject terms, including short acronyms such as ML and AI."""
    return {
        term for term in re.findall(r"\w+", topic.casefold())
        if len(term) > 1 and term not in GENERATION_GENERIC_TERMS
    }


def handle_generation_request_node(state: ChatWorkflowState) -> ChatWorkflowState:
    requested_format = state.get("requested_format")
    params = state.get("request_params") or {}

    if requested_format not in REQUIRED_PARAMS_BY_FORMAT:
        message = (
            "I detected a document generation request, but couldn't determine a "
            "supported format (PDF, DOCX, CSV, or TXT). Could you specify one?"
        )
        return {**state, "answer": message}

    if requested_format not in SUPPORTED_FORMATS:
        message = (
            f"I detected a request to generate a {requested_format.upper()} file, "
            "but that format isn't implemented yet."
        )
        return {**state, "answer": message}

    topic = params.get("topic") or params.get("title") or state.get("user_message", "uploaded documents")

    try:
        chunks = retrieve_document_context(
            str(topic), original_query=state.get("user_message", str(topic)),
            filters=state.get("retrieval_filters"),
        )
    except Exception as exc:
        logger.warning("generation.retrieval_failed error=%s", exc)
        chunks = []

    if not chunks:
        message = (
            "There is no data in the indexed files about that subject, so I did not "
            "generate a file. Upload and index a relevant document, or try another topic."
        )
        return {**state, "answer": message}

    subject_terms = _generation_topic_terms(str(topic))
    source_terms = set(re.findall(r"\w+", " ".join(str(chunk.get("content") or "") for chunk in chunks).casefold()))
    if subject_terms and not subject_terms.issubset(source_terms):
        return {
            **state,
            "answer": "There is no data in the indexed files about that subject, so I did not generate a file.",
        }

    body_paragraphs = [
        f"{str(chunk.get('file_path') or chunk.get('document_id') or 'Indexed document').split('/')[-1]}: "
        f"{str(chunk.get('content', '')).strip()}"
        for chunk in chunks if str(chunk.get("content", "")).strip()
    ]
    if not body_paragraphs:
        return {**state, "answer": "The indexed files contained no extractable text for this export."}
    source_note = "Content sourced from your indexed documents."


    preview_text = "\n\n".join(body_paragraphs[:2])
    if len(preview_text) > 500:
        preview_text = preview_text[:500].rstrip() + "..."

    try:
        if requested_format == "csv":
            filename, _ = generate_csv(params, chunks)
        elif requested_format == "pdf":
            filename = generate_pdf(params, body_paragraphs, source_note)
        elif requested_format == "txt":
            filename = generate_txt(params, body_paragraphs, source_note)
        elif requested_format == "docx":
            filename = generate_docx(params, body_paragraphs, source_note)
        else:
            raise RuntimeError(f"No generator wired for format={requested_format}")
    except Exception as exc:
        logger.warning("generation.file_build_failed format=%s error=%s", requested_format, exc)
        return {**state, "answer": f"I collected all your parameters but hit an error building the {requested_format.upper()}: {exc}"}

    download_link = f"/api/chatbot/generate/download/{filename}"
    summary = (
        f"Your {requested_format.upper()} is ready — \"{params.get('title') or topic}\". {source_note}\n\n"
        f"**Preview:**\n> {preview_text}\n\n"
        f"[Download {requested_format.upper()}]({download_link})"
    )
    return {**state, "answer": summary}

def route_after_analysis(state: ChatWorkflowState) -> str:
    if state.get("request_type") == "generation":
        return "handle_generation_request"
    return "optimize_query"


def optimize_query_node(state: ChatWorkflowState) -> ChatWorkflowState:
    payload = QueryOptimizerInput(
        user_message=state.get("user_message", ""),
        recent_messages=state.get("recent_messages", []),
        session_summary=state.get("session_summary"),
        long_term_memory=state.get("long_term_memory", []),
        session_id=state.get("session_id"),
        user_id=state.get("user_id"),
    )
    try:
        result = optimize_query(payload)
        save_query_optimization_run(
            result=result,
            session_id=state.get("session_id"),
            user_id=state.get("user_id"),
        )
    except Exception as exc:
        logger.warning("query_optimizer.integration_failed error=%s", exc)
        fallback_query = state.get("user_message", "").strip()
        return {
            **state,
            "optimized_query": fallback_query,
            "query_optimization": {
                "original_query": state.get("user_message", ""),
                "optimized_query": fallback_query,
                "route_type": "simple",
                "strategy": "workflow_fallback_direct_retrieval",
                "confidence": 0.0,
                "variants": [],
                "sub_questions": [],
                "used_llm": False,
                "reason": f"Query optimizer failed in workflow: {exc}",
            },
            "query_route_type": "simple",
            "query_variants": [],
            "query_sub_questions": [],
        }

    return {
        **state,
        "optimized_query": result.optimized_query,
        "query_optimization": result.to_dict(),
        "query_route_type": result.route_type,
        "query_variants": result.variants,
        "query_sub_questions": result.sub_questions,
    }


def summarize_history_node(state: ChatWorkflowState) -> ChatWorkflowState:
    """Graph-controlled summarization step for the current session."""
    summary_result = apply_summarization_policy(
        previous_summary=state.get("session_summary"),
        recent_messages=state.get("recent_messages", []),
    )
    updated_summary_record = state.get("session_summary_record")
    if summary_result["summary_updated"] and summary_result["summary_text"]:
        updated_summary_record = save_session_summary(
            session_id=str(state.get("session_id", "")),
            summary_text=str(summary_result["summary_text"]),
            summary_record=state.get("session_summary_record"),
        )
    return {
        **state,
        "recent_messages": summary_result["recent_messages"],
        "session_summary": summary_result["summary_text"],
        "session_summary_record": updated_summary_record,
    }


def load_memory_node(state: ChatWorkflowState) -> ChatWorkflowState:
    memories = load_relevant_memory(
        user_id=state.get("user_id", ""),
        query=state.get("optimized_query", state.get("user_message", "")),
    )
    return {
        **state,
        "long_term_memory": memories,
    }


def retrieve_documents_node(state: ChatWorkflowState) -> ChatWorkflowState:
    chunks = retrieve_document_context(
        state.get("optimized_query", ""),
        original_query=state.get("user_message", ""),
        variants=state.get("query_variants"),
        sub_questions=state.get("query_sub_questions"),
        filters=state.get("retrieval_filters"),
    )
    return {
        **state,
        "retrieved_chunks": chunks,
    }


def build_context_node(state: ChatWorkflowState) -> ChatWorkflowState:
    context = build_context(
        user_query=state.get("user_message", ""),
        optimized_query=state.get("optimized_query"),
        session_summary=state.get("session_summary"),
        recent_messages=state.get("recent_messages", []),
        long_term_memory=state.get("long_term_memory", []),
        retrieved_chunks=state.get("retrieved_chunks", []),
    )
    return {
        **state,
        "context": context,
    }


def generate_answer_node(state: ChatWorkflowState) -> ChatWorkflowState:
    answer = build_answer_from_context(state.get("context", {}))
    return {
        **state,
        "answer": answer,
    }


def update_memory_node(state: ChatWorkflowState) -> ChatWorkflowState:
    candidate = build_memory_candidate(
        user_id=state.get("user_id", ""),
        session_id=state.get("session_id"),
        recent_messages=state.get("recent_messages", []),
        user_message=state.get("user_message", ""),
        assistant_answer=state.get("answer", ""),
    )
    return {
        **state,
        "memory_candidate": candidate,
    }


def run_chat_workflow(initial_state: ChatWorkflowState) -> ChatWorkflowState:
    """Run the workflow with LangGraph when available, otherwise sequentially."""
    try:
        workflow = build_chat_workflow()
        return workflow.invoke(initial_state)
    except RuntimeError:
        state = load_session_node(initial_state)
        state = analyze_request_node(state)
        if state.get("request_type") == "generation":
            return handle_generation_request_node(state)
        state = optimize_query_node(state)
        state = summarize_history_node(state)
        state = load_memory_node(state)
        state = retrieve_documents_node(state)
        state = build_context_node(state)
        state = generate_answer_node(state)
        state = update_memory_node(state)
        return state


def build_chat_workflow():
    """Create the chatbot LangGraph workflow.

    Login is intentionally outside this graph.
    SummarizationMiddleware should wrap chat history before this workflow runs.
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph is not installed yet. Install it before building the chatbot workflow."
        ) from exc

    graph = StateGraph(ChatWorkflowState)
    graph.add_node("analyze_request", analyze_request_node)
    graph.add_node("handle_generation_request", handle_generation_request_node)
    graph.add_node("load_session", load_session_node)
    graph.add_node("optimize_query", optimize_query_node)
    graph.add_node("summarize_history", summarize_history_node)
    graph.add_node("load_memory", load_memory_node)
    graph.add_node("retrieve_documents", retrieve_documents_node)
    graph.add_node("build_context", build_context_node)
    graph.add_node("generate_answer", generate_answer_node)
    graph.add_node("update_memory", update_memory_node)

    graph.add_edge(START, "load_session")
    graph.add_edge("load_session", "analyze_request")
    graph.add_conditional_edges(
        "analyze_request",
        route_after_analysis,
        {"optimize_query": "optimize_query", "handle_generation_request": "handle_generation_request"},
    )
    graph.add_edge("handle_generation_request", END)
    graph.add_edge("optimize_query", "summarize_history")
    graph.add_edge("summarize_history", "load_memory")
    graph.add_edge("load_memory", "retrieve_documents")
    graph.add_edge("retrieve_documents", "build_context")
    graph.add_edge("build_context", "generate_answer")
    graph.add_edge("generate_answer", "update_memory")
    graph.add_edge("update_memory", END)

    return graph.compile()
