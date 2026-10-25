"""LangGraph workflow assembly coordinating end-to-end CareerPilot application lifecycle."""

import logging
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.services.workflow.nodes import (
    deduplicate_job_node,
    discover_job_node,
    generate_documents_node,
    human_approval_node,
    match_candidate_node,
    normalize_job_node,
    prepare_application_node,
    submit_or_handoff_node,
    tracking_node,
    validate_quality_node,
)
from app.services.workflow.schemas import WorkflowState

logger = logging.getLogger(__name__)


def route_after_discovery(state: WorkflowState) -> str:
    """Conditional router after job discovery."""
    if state.get("status") == "failed" or not state.get("job_data"):
        return END
    return "normalize_job"


def route_after_deduplication(state: WorkflowState) -> str:
    """Conditional router after job deduplication."""
    if state.get("status") == "failed" or not state.get("job_id"):
        return END
    return "match_candidate"


def route_after_matching(state: WorkflowState) -> str:
    """Conditional router after candidate deterministic matching."""
    if not state.get("meets_threshold", False) or state.get("status") == "failed":
        return END
    return "generate_documents"


def route_after_generation(state: WorkflowState) -> str:
    """Conditional router after resume and letter generation."""
    if state.get("status") == "failed":
        return END
    return "validate_quality"


def route_after_validation(state: WorkflowState) -> str:
    """Conditional router after quality and factual validation."""
    if not state.get("validation_passed", False) or state.get("status") == "failed":
        return END
    return "prepare_application"


def route_after_approval(state: WorkflowState) -> str:
    """Conditional router enforcing human approval before submission."""
    # STRICT SECURITY CHECK: Submission is strictly barred unless human explicitly approved
    if state.get("human_approved") is True and state.get("status") == "approved":
        return "submit_or_handoff"
    return END


def build_workflow_graph() -> StateGraph:
    """Build uncompiled StateGraph with explicit nodes and conditional edges."""
    builder = StateGraph(WorkflowState)

    # 1. Register explicit nodes
    builder.add_node("discover_job", discover_job_node)
    builder.add_node("normalize_job", normalize_job_node)
    builder.add_node("deduplicate_job", deduplicate_job_node)
    builder.add_node("match_candidate", match_candidate_node)
    builder.add_node("generate_documents", generate_documents_node)
    builder.add_node("validate_quality", validate_quality_node)
    builder.add_node("prepare_application", prepare_application_node)
    builder.add_node("human_approval", human_approval_node)
    builder.add_node("submit_or_handoff", submit_or_handoff_node)
    builder.add_node("tracking", tracking_node)

    # 2. Add edges and conditional branches
    builder.add_edge(START, "discover_job")
    builder.add_conditional_edges("discover_job", route_after_discovery)
    builder.add_edge("normalize_job", "deduplicate_job")
    builder.add_conditional_edges("deduplicate_job", route_after_deduplication)
    builder.add_conditional_edges("match_candidate", route_after_matching)
    builder.add_conditional_edges("generate_documents", route_after_generation)
    builder.add_conditional_edges("validate_quality", route_after_validation)
    builder.add_edge("prepare_application", "human_approval")
    builder.add_conditional_edges("human_approval", route_after_approval)
    builder.add_edge("submit_or_handoff", "tracking")
    builder.add_edge("tracking", END)

    return builder


def compile_workflow_graph(
    checkpointer: BaseCheckpointSaver[Any],
) -> CompiledStateGraph:
    """Compile graph with durable checkpointer."""
    builder = build_workflow_graph()
    return builder.compile(checkpointer=checkpointer)
