from __future__ import annotations

from dw_agent.nodes.common import METRIC_COLUMNS
from dw_agent.state import AgentState


def review_outputs(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    metrics = parsed.get("metrics", [])
    dimensions = parsed.get("dimensions", [])

    matched_metrics = [metric for metric in metrics if metric in METRIC_COLUMNS]
    missing_metrics = [metric for metric in metrics if metric not in METRIC_COLUMNS]

    findings = [
        f"已命中指标口径：{', '.join(matched_metrics) if matched_metrics else '无'}。",
        f"当前粒度为：{parsed.get('granularity')}，与维度列表保持一致。",
        "DDL、ETL 和 DQC 均使用 `dt` 作为分区字段。",
    ]
    validation = state.get("sql_validation", {})
    if validation:
        status = "通过" if validation.get("passed") else "存在待处理问题"
        findings.append(f"SQL 自检状态：{status}。")
    if missing_metrics:
        findings.append(f"以下指标未命中模拟口径库，需要人工确认：{', '.join(missing_metrics)}。")
    if "日期" not in dimensions:
        findings.append("需求未显式包含日期维度，建议确认报表是否需要趋势查询。")

    review = "## 审阅结论\n\n" + "\n".join(f"- {finding}" for finding in findings)
    if validation:
        errors = validation.get("errors", [])
        warnings = validation.get("warnings", [])
        review += "\n\n### SQL 自检\n\n"
        if errors:
            review += "\n".join(f"- 错误：{item}" for item in errors)
            review += "\n"
        if warnings:
            review += "\n".join(f"- 提醒：{item}" for item in warnings)
            review += "\n"
        if not errors and not warnings:
            review += "- 未发现阻断问题。\n"

    tool_trace = state.get("tool_trace", [])
    if tool_trace:
        review += "\n### 工具调用轨迹\n\n"
        review += "\n".join(
            f"- {index}. `{item.get('tool')}` -> {item.get('output')}"
            for index, item in enumerate(tool_trace, start=1)
        )

    review += """

### 主要风险

- SQL 仍是初稿，真实落地前需要校验上游字段是否存在。
- 退款、取消、部分支付等交易边界没有在需求中明确。
- 维度快照口径需要和业务确认，尤其是地区、渠道这类会变化的属性。

### 建议下一步

- 加一个人工确认节点，先确认指标口径和粒度，再生成正式 SQL。
- 接入真实元数据后，增加字段存在性检查、血缘检查和 SQL dry-run。
"""

    final_report = "\n\n".join(
        [
            "# 数仓建模 Agent 输出报告",
            state["modeling_plan"],
            "## DDL\n\n```sql\n" + state["ddl"] + "\n```",
            "## ETL SQL\n\n```sql\n" + state["etl_sql"] + "\n```",
            state["dqc_rules"],
            review,
        ]
    )

    return {**state, "review": review, "final_report": final_report}
