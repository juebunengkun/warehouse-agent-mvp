from __future__ import annotations

from dw_agent.state import AgentState


def clarify_requirement(state: AgentState) -> AgentState:
    plan = state.get("agent_plan", {})
    questions = list(plan.get("clarification_questions", []))
    default_assumptions = _default_assumptions(questions)
    clarification = {
        "need_clarification": bool(plan.get("need_clarification")),
        "questions": questions,
        "blocking": bool(questions),
        "default_assumptions": default_assumptions,
        "human_review_required": bool(questions),
    }

    trace = {
        "tool": "clarification_guard",
        "input": {"need_clarification": plan.get("need_clarification", False)},
        "output": {
            "blocking": clarification["blocking"],
            "question_count": len(questions),
        },
    }
    return {
        **state,
        "clarification": clarification,
        "clarification_questions": [*state.get("clarification_questions", []), *questions],
        "tool_trace": [*state.get("tool_trace", []), trace],
    }


def _default_assumptions(questions: list[str]) -> list[str]:
    assumptions = []
    joined = " ".join(questions).lower()
    if "payment amount" in joined or "支付金额" in joined:
        assumptions.append("Default payment amount is counted by successful payment time.")
    if "new/existing" in joined or "新老用户" in joined:
        assumptions.append("Default new/existing user type follows the user profile dimension table.")
    if "refund rate" in joined or "退款率" in joined:
        assumptions.append("Default refund rate is refund amount divided by payment amount.")
    if "refresh cycle" in joined:
        assumptions.append("Default refresh cycle is T+1 daily batch.")
    if not assumptions:
        assumptions.append("No blocking assumption detected; keep generated output under human review.")
    return assumptions
