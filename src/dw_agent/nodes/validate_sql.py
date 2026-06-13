from __future__ import annotations

from dw_agent.mcp_client import call_mcp_tool
from dw_agent.state import AgentState


def validate_sql(state: AgentState) -> AgentState:
    validation = call_mcp_tool(
        "validate_sql_tool",
        {
            "ddl": state.get("ddl", ""),
            "etl_sql": state.get("etl_sql", ""),
            "parsed_requirement": {**state["parsed"], "reuse_decision": state.get("reuse_decision", {})},
        },
    )
    trace = {
        "tool": "mcp.validate_sql_tool",
        "input": {
            "dimensions": state["parsed"].get("dimensions", []),
            "metrics": state["parsed"].get("metrics", []),
        },
        "output": {
            "passed": validation.get("passed"),
            "error_count": len(validation.get("errors", [])),
            "warning_count": len(validation.get("warnings", [])),
        },
    }
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
