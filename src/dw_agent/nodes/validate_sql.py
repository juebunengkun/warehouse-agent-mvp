from __future__ import annotations

from dw_agent.state import AgentState
from dw_agent.tools import sql_validation_tool


def validate_sql(state: AgentState) -> AgentState:
    validation, trace = sql_validation_tool(state.get("ddl", ""), state.get("etl_sql", ""), state["parsed"])
    return {
        **state,
        "sql_validation": validation,
        "tool_trace": [*state.get("tool_trace", []), trace],
    }


def route_after_sql_validation(state: AgentState) -> str:
    validation = state.get("sql_validation", {})
    if validation.get("passed") or state.get("validation_attempts", 0) >= 1:
        return "continue"
    return "rewrite"
