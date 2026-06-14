from __future__ import annotations

from dw_agent.nodes.generate_ddl import generate_ddl
from dw_agent.nodes.generate_etl import generate_etl
from dw_agent.nodes.verify_outputs import MAX_REWRITE_COUNT
from dw_agent.state import AgentState


def rewrite_sql(state: AgentState) -> AgentState:
    rewrite_count = state.get("rewrite_count", 0)
    if rewrite_count >= MAX_REWRITE_COUNT:
        return {
            **state,
            "tool_trace": [
                *state.get("tool_trace", []),
                {
                    "tool": "sql_rewrite",
                    "input": {"rewrite_count": rewrite_count},
                    "output": {"strategy": "skipped_rewrite_limit_reached"},
                },
            ],
        }
    validation = state.get("sql_validation", {})
    style_review = state.get("sql_style_review", {})
    preview = state.get("sql_preview", {})
    verification = state.get("verification_result", {})
    notes = [
        *validation.get("errors", []),
        *validation.get("warnings", []),
        *[item.get("message", item.get("rule", "")) for item in style_review.get("issues", [])],
        *preview.get("errors", []),
        *verification.get("blocking_issues", []),
    ]
    tool_trace = [
        *state.get("tool_trace", []),
        {
            "tool": "sql_rewrite",
            "input": {"rewrite_count": rewrite_count, "validation_notes": [note for note in notes if note]},
            "output": {"strategy": "regenerate_ddl_and_etl_from_confirmed_state"},
        },
    ]

    regenerated = generate_ddl({**state, "tool_trace": tool_trace})
    regenerated = generate_etl(regenerated)
    return {
        **regenerated,
        "tool_trace": tool_trace,
        "validation_attempts": state.get("validation_attempts", 0) + 1,
        "rewrite_count": rewrite_count + 1,
    }
