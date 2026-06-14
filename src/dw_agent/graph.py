from __future__ import annotations

from pathlib import Path

from langgraph.graph import END, StateGraph

from dw_agent.config import DEFAULT_KB_PATH
from dw_agent.nodes.clarify_requirement import clarify_requirement
from dw_agent.nodes.decide_modeling_strategy import decide_modeling_strategy
from dw_agent.nodes.decide_table_reuse import decide_table_reuse
from dw_agent.nodes.generate_ddl import generate_ddl
from dw_agent.nodes.generate_dqc import generate_dqc
from dw_agent.nodes.generate_etl import generate_etl
from dw_agent.nodes.generate_modeling import generate_modeling
from dw_agent.nodes.load_memory import load_memory_context
from dw_agent.nodes.parse_requirement import parse_requirement
from dw_agent.nodes.plan_task import plan_task
from dw_agent.nodes.retrieve_context import retrieve_context
from dw_agent.nodes.review import review_outputs
from dw_agent.nodes.review_sql_style import review_sql_style
from dw_agent.nodes.rewrite_sql import rewrite_sql
from dw_agent.nodes.route_requirement import route_after_requirement, route_requirement
from dw_agent.nodes.save_memory import save_memory_context
from dw_agent.nodes.sql_preview import sql_preview
from dw_agent.nodes.tool_router import tool_router
from dw_agent.nodes.validate_sql import validate_sql
from dw_agent.nodes.verify_outputs import route_after_verification, verify_outputs
from dw_agent.state import AgentState


def build_requirement_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("parse_requirement", parse_requirement)
    workflow.add_node("load_memory_context", load_memory_context)
    workflow.add_node("plan_task", plan_task)
    workflow.add_node("clarify_requirement", clarify_requirement)
    workflow.add_node("route_requirement", route_requirement)

    workflow.set_entry_point("parse_requirement")
    workflow.add_edge("parse_requirement", "load_memory_context")
    workflow.add_edge("load_memory_context", "plan_task")
    workflow.add_edge("plan_task", "clarify_requirement")
    workflow.add_edge("clarify_requirement", "route_requirement")
    workflow.add_edge("route_requirement", END)
    return workflow.compile()


def build_context_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("tool_router", tool_router)
    workflow.add_node("retrieve_context", retrieve_context)
    workflow.add_node("decide_table_reuse", decide_table_reuse)

    workflow.set_entry_point("tool_router")
    workflow.add_edge("tool_router", "retrieve_context")
    workflow.add_edge("retrieve_context", "decide_table_reuse")
    workflow.add_edge("decide_table_reuse", END)
    return workflow.compile()


def build_generation_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("decide_modeling_strategy", decide_modeling_strategy)
    workflow.add_node("generate_modeling", generate_modeling)
    workflow.add_node("generate_ddl", generate_ddl)
    workflow.add_node("generate_etl", generate_etl)

    workflow.set_entry_point("decide_modeling_strategy")
    workflow.add_edge("decide_modeling_strategy", "generate_modeling")
    workflow.add_edge("generate_modeling", "generate_ddl")
    workflow.add_edge("generate_ddl", "generate_etl")
    workflow.add_edge("generate_etl", END)
    return workflow.compile()


def build_validation_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("validate_sql", validate_sql)
    workflow.add_node("review_sql_style", review_sql_style)
    workflow.add_node("sql_preview", sql_preview)
    workflow.add_node("verify_outputs", verify_outputs)
    workflow.add_node("rewrite_sql", rewrite_sql)

    workflow.set_entry_point("validate_sql")
    workflow.add_edge("validate_sql", "review_sql_style")
    workflow.add_edge("review_sql_style", "sql_preview")
    workflow.add_edge("sql_preview", "verify_outputs")
    workflow.add_conditional_edges(
        "verify_outputs",
        route_after_verification,
        {
            "rewrite": "rewrite_sql",
            "continue": END,
        },
    )
    workflow.add_edge("rewrite_sql", "validate_sql")
    return workflow.compile()


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("requirement_subgraph", build_requirement_graph())
    workflow.add_node("context_subgraph", build_context_graph())
    workflow.add_node("generation_subgraph", build_generation_graph())
    workflow.add_node("validation_subgraph", build_validation_graph())
    workflow.add_node("generate_dqc", generate_dqc)
    workflow.add_node("verify_outputs_final", verify_outputs)
    workflow.add_node("review_outputs", review_outputs)
    workflow.add_node("save_memory_context", save_memory_context)

    workflow.set_entry_point("requirement_subgraph")
    workflow.add_conditional_edges(
        "requirement_subgraph",
        route_after_requirement,
        {
            "awaiting_user_confirmation": END,
            "continue_generation": "context_subgraph",
        },
    )
    workflow.add_edge("context_subgraph", "generation_subgraph")
    workflow.add_edge("generation_subgraph", "validation_subgraph")
    workflow.add_edge("validation_subgraph", "generate_dqc")
    workflow.add_edge("generate_dqc", "verify_outputs_final")
    workflow.add_edge("verify_outputs_final", "review_outputs")
    workflow.add_edge("review_outputs", "save_memory_context")
    workflow.add_edge("save_memory_context", END)

    return workflow.compile()


GRAPH = build_graph()


def run_agent(
    requirement: str,
    knowledge_base_path: str | Path | None = None,
    *,
    require_confirmation: bool = False,
    approved_parsed: dict | None = None,
) -> AgentState:
    kb_path = Path(knowledge_base_path) if knowledge_base_path else DEFAULT_KB_PATH
    initial_state: AgentState = {
        "requirement": requirement.strip(),
        "knowledge_base_path": str(kb_path),
        "auto_confirm": not require_confirmation,
        "human_confirmed": approved_parsed is not None,
        "validation_attempts": 0,
        "rewrite_count": 0,
    }
    if approved_parsed:
        initial_state["parsed"] = approved_parsed
    return GRAPH.invoke(initial_state)
