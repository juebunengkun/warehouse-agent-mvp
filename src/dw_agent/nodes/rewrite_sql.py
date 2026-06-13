from __future__ import annotations

from dw_agent.nodes.generate_ddl import generate_ddl
from dw_agent.nodes.generate_etl import generate_etl
from dw_agent.state import AgentState


def rewrite_sql(state: AgentState) -> AgentState:
    validation = state.get("sql_validation", {})
    notes = validation.get("errors", []) + validation.get("warnings", [])
    tool_trace = [
        *state.get("tool_trace", []),
        {
            "tool": "sql_rewrite",
            "input": {"validation_notes": notes},
            "output": {"strategy": "regenerate_ddl_and_etl_from_confirmed_state"},
        },
    ]

    regenerated = generate_ddl({**state, "tool_trace": tool_trace})
    regenerated = generate_etl(regenerated)
    return {
        **regenerated,
        "tool_trace": tool_trace,
        "validation_attempts": state.get("validation_attempts", 0) + 1,
    }
