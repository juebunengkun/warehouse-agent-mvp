from __future__ import annotations

from dw_agent.state import AgentState

MAX_REWRITE_COUNT = 1


def verify_outputs(state: AgentState) -> AgentState:
    validation = state.get("sql_validation", {})
    style_review = state.get("sql_style_review", {})
    preview = state.get("sql_preview", {})
    clarification = state.get("clarification", {})
    reuse_decision = state.get("reuse_decision", {})

    blocking_issues: list[str] = []
    warnings: list[str] = []

    if validation and not validation.get("passed", False):
        blocking_issues.extend(validation.get("errors", []) or ["SQL validation failed."])

    style_errors = [
        issue.get("message", issue.get("rule", "SQL style error"))
        for issue in style_review.get("issues", [])
        if issue.get("level") == "error"
    ]
    blocking_issues.extend(style_errors)

    if preview.get("preview_available") and not preview.get("passed"):
        blocking_issues.extend(preview.get("errors", []) or ["SQL preview failed."])
    elif not preview.get("preview_available"):
        warnings.extend(preview.get("warnings", []) or [preview.get("reason", "SQL preview skipped.")])

    if preview.get("row_count") == 0 and preview.get("preview_available"):
        warnings.append("SQL preview returned zero rows; verify partition and demo data coverage.")
    warnings.extend(preview.get("warnings", []))

    need_human_review = bool(clarification.get("blocking")) or _reuse_has_risk(reuse_decision)
    need_rewrite = bool(blocking_issues) and state.get("rewrite_count", 0) < MAX_REWRITE_COUNT
    if blocking_issues and state.get("rewrite_count", 0) >= MAX_REWRITE_COUNT:
        need_human_review = True
        warnings.append("Rewrite limit reached; manual SQL review is required.")

    result = {
        "passed": not blocking_issues,
        "need_rewrite": need_rewrite,
        "need_human_review": need_human_review,
        "checks": {
            "sql_parse": "passed" if validation.get("passed") else "failed",
            "sql_style": "passed" if style_review.get("passed") else "failed",
            "sql_preview": _preview_status(preview),
            "dqc": "generated" if state.get("dqc_rules") else "pending",
            "modeling_strategy": "generated" if state.get("modeling_strategy") else "missing",
        },
        "blocking_issues": blocking_issues,
        "warnings": _dedupe(warnings),
        "suggested_next_action": _next_action(need_rewrite, need_human_review, blocking_issues),
        "rewrite_count": state.get("rewrite_count", 0),
        "max_rewrite_count": MAX_REWRITE_COUNT,
    }

    trace = {
        "tool": "verify_outputs",
        "input": {"rewrite_count": state.get("rewrite_count", 0)},
        "output": {
            "passed": result["passed"],
            "need_rewrite": result["need_rewrite"],
            "need_human_review": result["need_human_review"],
            "blocking_issue_count": len(blocking_issues),
        },
    }
    return {**state, "verification_result": result, "tool_trace": [*state.get("tool_trace", []), trace]}


def route_after_verification(state: AgentState) -> str:
    verification = state.get("verification_result", {})
    if verification.get("need_rewrite") and state.get("rewrite_count", 0) < MAX_REWRITE_COUNT:
        return "rewrite"
    return "continue"


def _preview_status(preview: dict) -> str:
    if not preview:
        return "skipped"
    if not preview.get("preview_available"):
        return "skipped"
    return "passed" if preview.get("passed") else "failed"


def _reuse_has_risk(reuse_decision: dict) -> bool:
    checks = reuse_decision.get("hard_checks", {})
    if not checks:
        return False
    risky_checks = ["grain_matched", "metric_semantics_matched", "business_process_matched", "partition_available"]
    return any(checks.get(name) is False for name in risky_checks)


def _next_action(need_rewrite: bool, need_human_review: bool, blocking_issues: list[str]) -> str:
    if need_rewrite:
        return "rewrite_sql"
    if need_human_review or blocking_issues:
        return "human_review"
    return "continue_to_dqc"


def _dedupe(values: list[str]) -> list[str]:
    result = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result
