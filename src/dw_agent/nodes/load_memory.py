from __future__ import annotations

from dw_agent.memory import load_relevant_sessions
from dw_agent.state import AgentState


def load_memory_context(state: AgentState) -> AgentState:
    parsed = state.get("parsed", {})
    memory_context = load_relevant_sessions(parsed, limit=3)
    trace = [
        *state.get("tool_trace", []),
        {
            "tool": "sqlite.load_relevant_sessions",
            "input": {
                "business_theme": parsed.get("business_theme"),
                "metrics": parsed.get("metrics", []),
                "dimensions": parsed.get("dimensions", []),
            },
            "output": {
                "match_count": len(memory_context),
                "session_ids": [item["id"] for item in memory_context],
            },
        },
    ]
    return {**state, "memory_context": memory_context, "tool_trace": trace}
