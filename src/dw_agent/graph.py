from __future__ import annotations

from pathlib import Path

from langgraph.graph import END, StateGraph

from dw_agent.config import DEFAULT_KB_PATH
from dw_agent.nodes.generate_ddl import generate_ddl
from dw_agent.nodes.generate_dqc import generate_dqc
from dw_agent.nodes.generate_etl import generate_etl
from dw_agent.nodes.generate_modeling import generate_modeling
from dw_agent.nodes.parse_requirement import parse_requirement
from dw_agent.nodes.retrieve_context import retrieve_context
from dw_agent.nodes.rewrite_sql import rewrite_sql
from dw_agent.nodes.route_requirement import route_after_requirement, route_requirement
from dw_agent.nodes.review import review_outputs
from dw_agent.nodes.validate_sql import route_after_sql_validation, validate_sql
from dw_agent.state import AgentState


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("parse_requirement", parse_requirement)
    workflow.add_node("route_requirement", route_requirement)
    workflow.add_node("retrieve_context", retrieve_context)
    workflow.add_node("generate_modeling", generate_modeling)
    workflow.add_node("generate_ddl", generate_ddl)
    workflow.add_node("generate_etl", generate_etl)
    workflow.add_node("validate_sql", validate_sql)
    workflow.add_node("rewrite_sql", rewrite_sql)
    workflow.add_node("generate_dqc", generate_dqc)
    workflow.add_node("review_outputs", review_outputs)

    workflow.set_entry_point("parse_requirement")
    workflow.add_edge("parse_requirement", "route_requirement")
    workflow.add_conditional_edges(
        "route_requirement",
        route_after_requirement,
        {
            "awaiting_user_confirmation": END,
            "continue_generation": "retrieve_context",
        },
    )
    workflow.add_edge("retrieve_context", "generate_modeling")
    workflow.add_edge("generate_modeling", "generate_ddl")
    workflow.add_edge("generate_ddl", "generate_etl")
    workflow.add_edge("generate_etl", "validate_sql")
    workflow.add_conditional_edges(
        "validate_sql",
        route_after_sql_validation,
        {
            "rewrite": "rewrite_sql",
            "continue": "generate_dqc",
        },
    )
    workflow.add_edge("rewrite_sql", "validate_sql")
    workflow.add_edge("generate_dqc", "review_outputs")
    workflow.add_edge("review_outputs", END)

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
    }
    if approved_parsed:
        initial_state["parsed"] = approved_parsed
    return GRAPH.invoke(initial_state)
