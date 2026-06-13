from __future__ import annotations

import re
from typing import Any

import sqlglot
from sqlglot import exp

from dw_agent.state import AgentState

BAD_CTE_NAMES = {"base", "tmp", "t1", "t2", "final", "result"}


def review_sql_style(state: AgentState) -> AgentState:
    review = review_sql_style_text(state.get("etl_sql", ""))
    trace = {
        "tool": "sql_style_review",
        "input": {"sql_length": len(state.get("etl_sql", ""))},
        "output": {
            "passed": review["passed"],
            "issue_count": len(review["issues"]),
            "error_count": len([item for item in review["issues"] if item["level"] == "error"]),
        },
    }
    return {
        **state,
        "sql_style_review": review,
        "tool_trace": [*state.get("tool_trace", []), trace],
    }


def route_after_sql_style_review(state: AgentState) -> str:
    review = state.get("sql_style_review", {})
    has_error = any(item.get("level") == "error" for item in review.get("issues", []))
    if has_error and state.get("validation_attempts", 0) < 1:
        return "rewrite"
    return "continue"


def review_sql_style_text(sql: str) -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    sql_without_comments = _strip_line_comments(sql)

    _check_select_star(sql_without_comments, issues)
    _check_ctes(sql_without_comments, issues)
    _check_joins(sql_without_comments, issues)
    _check_group_by(sql_without_comments, issues)
    _check_division(sql_without_comments, issues)
    _check_insert_partition(sql_without_comments, issues)

    has_error = any(issue["level"] == "error" for issue in issues)
    return {"passed": not has_error, "issues": issues}


def _issue(issues: list[dict[str, str]], level: str, rule: str, message: str) -> None:
    issues.append({"level": level, "rule": rule, "message": message})


def _strip_line_comments(sql: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in sql.splitlines())


def _check_select_star(sql: str, issues: list[dict[str, str]]) -> None:
    if re.search(r"\bSELECT\s+\*", sql, flags=re.IGNORECASE):
        _issue(issues, "error", "NO_SELECT_STAR", "禁止 SELECT *，请显式列出字段。")


def _check_ctes(sql: str, issues: list[dict[str, str]]) -> None:
    cte_names = [name.lower() for name in re.findall(r"(?:WITH|,)\s+([a-zA-Z_][\w]*)\s+AS\s*\(", sql, re.IGNORECASE)]
    if len(cte_names) > 3:
        _issue(issues, "error", "MAX_CTE_COUNT", "CTE 超过 3 层，请拆成 DWD/DWS/ADS 或可复用中间表。")
    bad_names = sorted(set(cte_names) & BAD_CTE_NAMES)
    if bad_names:
        _issue(issues, "error", "BAD_CTE_NAME", f"CTE 命名缺少业务含义：{', '.join(bad_names)}。")


def _check_joins(sql: str, issues: list[dict[str, str]]) -> None:
    join_segments = re.finditer(
        r"(?P<join>(?:(?:LEFT|RIGHT|FULL|INNER|CROSS)\s+)?JOIN\s+(?P<table>[a-zA-Z_][\w.]*)(?P<body>.*?))"
        r"(?=\b(?:LEFT|RIGHT|FULL|INNER|CROSS)?\s*JOIN\b|\bWHERE\b|\bGROUP\s+BY\b|;|$)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for match in join_segments:
        join_text = match.group("join")
        table_name = match.group("table")
        if " ON " not in join_text.upper():
            _issue(issues, "error", "JOIN_REQUIRES_ON", f"JOIN {table_name} 缺少显式 ON 条件。")
        if table_name.lower().startswith("dim_") and not re.search(rf"{re.escape(table_name)}\.dt\s*=", join_text):
            _issue(issues, "error", "DIM_JOIN_REQUIRES_PARTITION", f"维表 {table_name} join 缺少 dt 分区条件。")
        if table_name.lower().startswith("dim_") and re.search(r"\bINNER\s+JOIN\b", join_text, flags=re.IGNORECASE):
            _issue(issues, "warn", "DIM_INNER_JOIN_RISK", f"维表 {table_name} 使用 INNER JOIN，可能过滤事实数据。")


def _check_group_by(sql: str, issues: list[dict[str, str]]) -> None:
    try:
        statements = [statement for statement in sqlglot.parse(sql, read="hive") if statement]
    except Exception:
        return
    for statement in statements:
        for select in statement.find_all(exp.Select):
            has_aggregate = any(expression.find(exp.AggFunc) for expression in select.expressions)
            if not has_aggregate:
                continue
            has_non_aggregate = any(not expression.find(exp.AggFunc) for expression in select.expressions)
            if has_non_aggregate and not select.args.get("group"):
                _issue(issues, "error", "AGGREGATE_REQUIRES_GROUP_BY", "聚合和非聚合字段混用时必须显式 GROUP BY。")


def _check_division(sql: str, issues: list[dict[str, str]]) -> None:
    if "/" not in sql:
        return
    if re.search(r"\b(CASE\s+WHEN|NULLIF)\b", sql, flags=re.IGNORECASE):
        return
    _issue(issues, "error", "DIVISION_REQUIRES_ZERO_GUARD", "存在除法表达式但未发现 CASE WHEN 或 NULLIF 除零保护。")


def _check_insert_partition(sql: str, issues: list[dict[str, str]]) -> None:
    for match in re.finditer(
        r"INSERT\s+OVERWRITE\s+TABLE\s+(?P<table>[a-zA-Z_][\w.]*)\s+(?P<body>.*?)(?=\bSELECT\b)",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        if "PARTITION" not in match.group("body").upper():
            _issue(
                issues, "error", "INSERT_REQUIRES_PARTITION", f"INSERT 目标表 {match.group('table')} 缺少 PARTITION。"
            )
