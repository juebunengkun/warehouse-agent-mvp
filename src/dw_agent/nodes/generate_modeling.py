from __future__ import annotations

from dw_agent.nodes.common import dimension_columns, markdown_table, metric_columns
from dw_agent.state import AgentState


def generate_modeling(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    strategy = state.get("modeling_strategy", {})
    metrics = parsed.get("metrics", [])
    dimensions = parsed.get("dimensions", [])
    grain = parsed.get("granularity", "待确认")
    reuse_decision = state.get("reuse_decision", {})

    plan = f"""## 建模方案

### 需求摘要

- 业务主题：{parsed.get("business_theme")}
- 业务过程：{strategy.get("business_process", "待确认")}
- 指标：{"、".join(metrics)}
- 维度：{"、".join(dimensions)}
- 粒度：{grain}
- 刷新周期：{parsed.get("refresh_cycle")}
- 时间范围：{parsed.get("time_range")}

### 事实表

{_table_section(strategy.get("fact_tables", []))}

### 维度表

{_table_section(strategy.get("dim_tables", []))}

### 汇总表

{_table_section(strategy.get("summary_tables", []), include_reuse=True)}

### 应用表

{_table_section(strategy.get("application_tables", []))}

### 维度字段

{markdown_table(["维度", "字段名", "类型", "说明"], _dimension_rows(dimensions))}

### 指标字段

{markdown_table(["指标", "字段名", "类型", "口径说明"], _metric_rows(metrics))}

### Join 方案

{_join_section(strategy.get("join_plan", []))}

### 依赖计划

{_dependency_section(strategy.get("dependency_plan", []))}

### 表复用判断

- 决策：{reuse_decision.get("decision", "未执行")}
- 推荐表：{reuse_decision.get("table") or "暂无"}
- 分数：{reuse_decision.get("score", "暂无")}
- 硬性检查：`{reuse_decision.get("hard_checks", {})}`
- 原因：{reuse_decision.get("reason", "未找到复用判断结果。")}

### 风险说明

{_risk_section(strategy.get("risk_notes", []))}

### 待人工确认

- 业务系统中无效订单、退款订单、取消订单是否计入指标。
- 地区、渠道、新老用户和会员等级是否以事件发生日快照为准。
- 客单价、转化率、ARPU 等派生指标的小数精度和除零规则。
"""
    return {**state, "modeling_plan": plan}


def _table_section(tables: list[dict], *, include_reuse: bool = False) -> str:
    if not tables:
        return "暂无规划表。"
    headers = ["表名", "层级", "类型", "粒度", "增全量", "SLA", "原因"]
    if include_reuse:
        headers.insert(5, "复用")
    rows = []
    for table in tables:
        row = [
            table.get("name", ""),
            table.get("layer", ""),
            table.get("table_type", ""),
            table.get("grain", ""),
            table.get("update_mode", ""),
            table.get("sla_time", ""),
            table.get("reason", ""),
        ]
        if include_reuse:
            row.insert(5, "是" if table.get("reuse") else "否")
        rows.append(row)
    return markdown_table(headers, rows)


def _dimension_rows(dimensions: list[str]) -> list[list[str]]:
    return [
        [dimension, field, sql_type, comment] for dimension, field, sql_type, comment in dimension_columns(dimensions)
    ]


def _metric_rows(metrics: list[str]) -> list[list[str]]:
    return [[metric, field, sql_type, comment] for metric, field, sql_type, comment in metric_columns(metrics)]


def _join_section(join_plan: list[dict]) -> str:
    if not join_plan:
        return "当前策略不需要额外维表关联，或已复用公共 DWS。"
    rows = [
        [
            item.get("left_table", ""),
            item.get("right_table", ""),
            item.get("join_type", ""),
            ", ".join(item.get("join_keys", [])),
            item.get("partition_condition", ""),
            item.get("risk", ""),
        ]
        for item in join_plan
    ]
    return markdown_table(["左表", "右表", "Join 类型", "关联键", "分区条件", "风险"], rows)


def _dependency_section(dependency_plan: list[str]) -> str:
    if not dependency_plan:
        return "- 暂无依赖计划。"
    return "\n".join(f"- {item}" for item in dependency_plan)


def _risk_section(risk_notes: list[str]) -> str:
    if not risk_notes:
        return "- 暂无新增风险。"
    return "\n".join(f"- {item}" for item in risk_notes)
