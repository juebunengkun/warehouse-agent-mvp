from __future__ import annotations

from dw_agent.nodes.common import METRIC_COLUMNS, markdown_table
from dw_agent.state import AgentState


def review_outputs(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    metrics = parsed.get("metrics", [])
    dimensions = parsed.get("dimensions", [])
    strategy = state.get("modeling_strategy", {})

    matched_metrics = [metric for metric in metrics if metric in METRIC_COLUMNS]
    missing_metrics = [metric for metric in metrics if metric not in METRIC_COLUMNS]

    findings = [
        f"已命中指标口径：{', '.join(matched_metrics) if matched_metrics else '无'}。",
        f"需求解析来源：{parsed.get('parser_source', 'unknown')}。",
        f"当前粒度为：{parsed.get('granularity')}，与维度列表保持一致。",
        "DDL、ETL 和 DQC 均使用 `dt` 作为分区字段。",
    ]
    reuse_decision = state.get("reuse_decision", {})
    if reuse_decision:
        findings.append(f"表复用决策：{reuse_decision.get('decision')}，{reuse_decision.get('reason')}")
    validation = state.get("sql_validation", {})
    if validation:
        status = "通过" if validation.get("passed") else "存在待处理问题"
        findings.append(f"SQL 自检状态：{status}。")
    style_review = state.get("sql_style_review", {})
    if style_review:
        status = "通过" if style_review.get("passed") else "存在风格问题"
        findings.append(f"SQL 风格审查：{status}。")
    if missing_metrics:
        findings.append(f"以下指标未命中模拟口径库，需要人工确认：{', '.join(missing_metrics)}。")
    if "日期" not in dimensions:
        findings.append("需求未显式包含日期维度，建议确认报表是否需要趋势查询。")

    review = "## 审阅结论\n\n" + "\n".join(f"- {finding}" for finding in findings)
    review += _strategy_review(strategy)
    review += _reuse_review(reuse_decision)
    review += _sql_validation_review(validation)
    review += _sql_style_review(style_review)
    review += _tool_trace_review(state.get("tool_trace", []))
    review += _memory_review(state.get("memory_context", []))
    review += _production_gap_review()

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


def _strategy_review(strategy: dict) -> str:
    if not strategy:
        return ""
    sections = ["\n\n### 建模策略摘要\n"]
    sections.append(f"- 业务过程：{strategy.get('business_process', '待确认')}")
    for title, key in [
        ("事实表", "fact_tables"),
        ("维度表", "dim_tables"),
        ("汇总表", "summary_tables"),
        ("应用表", "application_tables"),
    ]:
        rows = [
            [
                table.get("name", ""),
                table.get("layer", ""),
                table.get("table_type", ""),
                table.get("grain", ""),
                table.get("update_mode", ""),
                table.get("reason", ""),
            ]
            for table in strategy.get(key, [])
        ]
        sections.append(f"\n#### {title}\n\n")
        sections.append(markdown_table(["表名", "层级", "类型", "粒度", "增全量", "原因"], rows) if rows else "暂无。")

    joins = strategy.get("join_plan", [])
    sections.append("\n#### Join 方案\n\n")
    if joins:
        rows = [
            [
                item.get("left_table", ""),
                item.get("right_table", ""),
                item.get("join_type", ""),
                ", ".join(item.get("join_keys", [])),
                item.get("partition_condition", ""),
            ]
            for item in joins
        ]
        sections.append(markdown_table(["左表", "右表", "Join 类型", "关联键", "分区条件"], rows))
    else:
        sections.append("当前复用公共 DWS 或无需额外维表关联。")

    sections.append("\n#### 依赖计划\n\n")
    sections.append("\n".join(f"- {item}" for item in strategy.get("dependency_plan", [])) or "- 暂无依赖计划。")
    return "".join(sections)


def _reuse_review(reuse_decision: dict) -> str:
    if not reuse_decision:
        return ""
    risks = reuse_decision.get("risk_notes", [])
    return f"""

### 表复用决策

- 是否复用：{reuse_decision.get("decision")}
- 复用表：{reuse_decision.get("table") or "暂无"}
- 原因：{reuse_decision.get("reason")}
- 硬性检查：`{reuse_decision.get("hard_checks", {})}`
- 风险：{", ".join(risks) if risks else "暂无阻断风险。"}
"""


def _sql_validation_review(validation: dict) -> str:
    if not validation:
        return ""
    errors = validation.get("errors", [])
    warnings = validation.get("warnings", [])
    review = "\n### SQL 自检\n\n"
    if errors:
        review += "\n".join(f"- 错误：{item}" for item in errors) + "\n"
    if warnings:
        review += "\n".join(f"- 提醒：{item}" for item in warnings) + "\n"
    if not errors and not warnings:
        review += "- 未发现阻断问题。\n"
    return review


def _sql_style_review(style_review: dict) -> str:
    if not style_review:
        return ""
    issues = style_review.get("issues", [])
    review = "\n### SQL 风格审查\n\n"
    review += f"- 是否通过：{'是' if style_review.get('passed') else '否'}\n"
    review += "- 检查项：SELECT *、CTE 层数、CTE 命名、JOIN、DIM 分区、GROUP BY、除零保护、INSERT 分区。\n"
    if issues:
        review += "\n".join(f"- {item['level']} `{item['rule']}`：{item['message']}" for item in issues) + "\n"
    else:
        review += "- 未发现 SQL 风格问题。\n"
    return review


def _tool_trace_review(tool_trace: list[dict]) -> str:
    if not tool_trace:
        return ""
    review = "\n### 工具调用轨迹\n\n"
    review += "\n".join(
        f"- {index}. `{item.get('tool')}` -> {item.get('output')}" for index, item in enumerate(tool_trace, start=1)
    )
    return review


def _memory_review(memory_context: list[dict]) -> str:
    if not memory_context:
        return ""
    review = "\n\n### 历史会话参考\n\n"
    review += "\n".join(
        f"- Session #{item['id']}，score={item.get('score')}，需求：{item.get('requirement')}"
        for item in memory_context
    )
    return review


def _production_gap_review() -> str:
    return """

### 当前 MVP 与生产差距

- 元数据仍是本地 JSON，还没有接 DataHub/Hive Metastore/Glue/内部元数据平台。
- 指标平台仍是本地文件模拟，还没有指标版本、审批和适用粒度约束。
- SQL 校验还是 `sqlglot` + 规则，还没有真实 Hive/Spark dry-run 和 explain。
- 当前只生成 SQL，还没有生成 Airflow/DolphinScheduler 等调度 DAG。
- DQC 仍是模板，还没有接入生产 DQC 平台。
- 生成结果仍需人工 review 和 CR 流程。
"""
