from __future__ import annotations

from dw_agent.memory import save_session
from dw_agent.state import AgentState


def save_memory_context(state: AgentState) -> AgentState:
    session_id = save_session(dict(state))
    trace = [
        *state.get("tool_trace", []),
        {
            "tool": "sqlite.save_session",
            "input": {"requirement_length": len(state.get("requirement", ""))},
            "output": {"session_id": session_id},
        },
    ]
    return {**state, "session_id": session_id, "tool_trace": trace}
