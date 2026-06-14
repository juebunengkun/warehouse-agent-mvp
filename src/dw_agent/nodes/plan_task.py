from __future__ import annotations

from typing import Any

from dw_agent.nodes.common import DIMENSION_COLUMNS, METRIC_COLUMNS
from dw_agent.state import AgentState


def plan_task(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    metrics = parsed.get("metrics", [])
    dimensions = parsed.get("dimensions", [])
    missing_metrics = [metric for metric in metrics if metric not in METRIC_COLUMNS]
    missing_dimensions = [dimension for dimension in dimensions if dimension not in DIMENSION_COLUMNS]
    ambiguity_notes = _ambiguity_notes(parsed, state.get("requirement", ""))
    need_clarification = bool(missing_metrics or missing_dimensions or ambiguity_notes)

    plan: dict[str, Any] = {
        "goal": _goal(parsed),
        "need_clarification": need_clarification,
        "clarification_questions": _questions(missing_metrics, missing_dimensions, ambiguity_notes),
        "steps": [
            {
                "step": "parse_requirement",
                "purpose": "Extract metrics, dimensions, grain, time range, and refresh cycle.",
            },
            {"step": "search_metadata", "purpose": "Find candidate fact, dimension, summary, and application tables."},
            {"step": "decide_table_reuse", "purpose": "Decide whether existing DWS/ADS tables can be safely reused."},
            {"step": "decide_modeling_strategy", "purpose": "Plan DIM/DWD/DWS/ADS tables, dependencies, and joins."},
            {"step": "generate_sql", "purpose": "Generate DDL, ETL SQL, and DQC rules."},
            {"step": "review_sql_style", "purpose": "Review generated SQL against warehouse style rules."},
            {
                "step": "sql_preview",
                "purpose": "Run read-only DuckDB SELECT preview when a local demo database is available.",
            },
            {"step": "verify_outputs", "purpose": "Summarize validation, preview, DQC, and human-review risks."},
        ],
        "tools_needed": [
            "search_tables",
            "search_dimensions",
            "search_facts",
            "search_summaries",
            "review_sql_style",
            "sql_preview",
        ],
        "risk_notes": _risk_notes(missing_metrics, missing_dimensions, ambiguity_notes),
    }

    trace = {
        "tool": "agent_planner",
        "input": {
            "metrics": metrics,
            "dimensions": dimensions,
            "refresh_cycle": parsed.get("refresh_cycle"),
        },
        "output": {
            "need_clarification": plan["need_clarification"],
            "step_count": len(plan["steps"]),
            "tools_needed": plan["tools_needed"],
        },
    }
    return {**state, "agent_plan": plan, "tool_trace": [*state.get("tool_trace", []), trace]}


def _goal(parsed: dict) -> str:
    theme = parsed.get("business_theme") or "report"
    return f"Generate warehouse modeling plan, DDL, ETL SQL, DQC rules, and validation report for {theme}."


def _questions(missing_metrics: list[str], missing_dimensions: list[str], ambiguity_notes: list[str]) -> list[str]:
    questions = []
    if missing_metrics:
        questions.append(f"Please confirm metric semantics for: {', '.join(missing_metrics)}.")
    if missing_dimensions:
        questions.append(f"Please confirm dimension field mapping for: {', '.join(missing_dimensions)}.")
    questions.extend(ambiguity_notes)
    return questions


def _risk_notes(missing_metrics: list[str], missing_dimensions: list[str], ambiguity_notes: list[str]) -> list[str]:
    notes = []
    if missing_metrics:
        notes.append("Some metrics are not covered by the local metric dictionary.")
    if missing_dimensions:
        notes.append("Some dimensions are not covered by the local dimension dictionary.")
    notes.extend(ambiguity_notes)
    if not notes:
        notes.append("No blocking planning risk detected; generated SQL still requires human review before production.")
    return notes


def _ambiguity_notes(parsed: dict, requirement: str) -> list[str]:
    text = f"{requirement} {' '.join(parsed.get('metrics', []))} {' '.join(parsed.get('dimensions', []))}"
    notes = []
    if _contains_any(text, ["支付金额", "pay_amount", "GMV", "gmv"]):
        notes.append("Confirm whether payment amount is counted by order time or successful payment time.")
    if _contains_any(text, ["新老用户", "new user", "existing user"]):
        notes.append(
            "Confirm whether new/existing users are classified by registration time, first order time, or first visit time."
        )
    if _contains_any(text, ["退款率", "refund_rate"]):
        notes.append("Confirm whether refund rate uses refund amount/payment amount or refund orders/payment orders.")
    if not parsed.get("refresh_cycle") or "待确认" in str(parsed.get("refresh_cycle")):
        notes.append("Confirm whether the refresh cycle is T+1, hourly, real-time, weekly, or monthly.")
    return notes


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword.lower() in lowered for keyword in keywords)
