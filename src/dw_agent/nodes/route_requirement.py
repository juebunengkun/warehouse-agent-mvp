from __future__ import annotations

from dw_agent.nodes.common import DIMENSION_COLUMNS, METRIC_COLUMNS
from dw_agent.state import AgentState


def route_requirement(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    questions = _build_questions(parsed)

    if not state.get("auto_confirm") and not state.get("human_confirmed"):
        return {
            **state,
            "agent_decision": "awaiting_user_confirmation",
            "clarification_questions": questions or ["请确认解析出的指标、维度、粒度和刷新周期是否正确。"],
        }

    return {
        **state,
        "agent_decision": "continue_generation",
        "clarification_questions": questions,
    }


def route_after_requirement(state: AgentState) -> str:
    if state.get("agent_decision") == "awaiting_user_confirmation":
        return "awaiting_user_confirmation"
    return "continue_generation"


def _build_questions(parsed: dict) -> list[str]:
    questions: list[str] = []
    if not parsed.get("metrics"):
        questions.append("没有解析到明确指标，请补充要统计的指标。")
    if not parsed.get("dimensions"):
        questions.append("没有解析到明确维度，请补充统计维度。")
    if parsed.get("refresh_cycle") == "待确认":
        questions.append("刷新周期未明确，请确认是 T+1、小时级、实时还是月/周刷新。")
    if parsed.get("time_range") == "待确认":
        questions.append("查询时间范围未明确，请确认是否需要近 7 天、近 30 天或其他范围。")

    unknown_metrics = [metric for metric in parsed.get("metrics", []) if metric not in METRIC_COLUMNS]
    if unknown_metrics:
        questions.append(f"这些指标未命中模拟口径库，请确认口径：{', '.join(unknown_metrics)}。")

    unknown_dimensions = [dimension for dimension in parsed.get("dimensions", []) if dimension not in DIMENSION_COLUMNS]
    if unknown_dimensions:
        questions.append(f"这些维度未命中维度模板，请确认字段映射：{', '.join(unknown_dimensions)}。")

    if not questions:
        questions.append("我已经解析出需求，请确认指标、维度、粒度和刷新周期无误后继续生成。")
    return questions
