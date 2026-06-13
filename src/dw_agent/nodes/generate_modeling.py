from __future__ import annotations

from dw_agent.nodes.common import dimension_columns, markdown_table, metric_columns, table_names
from dw_agent.state import AgentState


def generate_modeling(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    names = table_names(parsed)
    metrics = parsed.get("metrics", [])
    dimensions = parsed.get("dimensions", [])
    grain = parsed.get("granularity", "待确认")
    time_range = parsed.get("time_range", "待确认")
    reuse_decision = state.get("reuse_decision", {})
    reuse_table = reuse_decision.get("table")
    dws_action = "复用已有汇总层" if reuse_decision.get("decision") == "reuse_existing_dws" else "新建/改造汇总层"

    layer_rows = [
        ["ODS", names["ods"], "原始事件粒度", "承接业务系统原始数据，保留原始字段和加载分区。"],
        ["DWD", names["dwd"], "订单/事件明细粒度", "清洗无效记录，统一字段命名，补充维度退化字段。"],
        ["DWS", reuse_table or names["dws"], grain, f"{dws_action}，按报表粒度聚合核心指标。"],
        ["ADS", names["ads"], grain, "面向报表展示，保留近周期查询字段和派生指标。"],
    ]

    dim_rows = [
        [dimension, field, sql_type, comment]
        for dimension, field, sql_type, comment in dimension_columns(dimensions)
    ]
    metric_rows = [
        [metric, field, sql_type, comment]
        for metric, field, sql_type, comment in metric_columns(metrics)
    ]

    plan = f"""## 建模方案

### 需求摘要

- 业务主题：{parsed.get("business_theme")}
- 指标：{"、".join(metrics)}
- 维度：{"、".join(dimensions)}
- 粒度：{grain}
- 刷新周期：{parsed.get("refresh_cycle")}
- 时间范围：{parsed.get("time_range")}

### 分层设计

{markdown_table(["层级", "建议表名", "数据粒度", "职责"], layer_rows)}

### 维度字段

{markdown_table(["维度", "字段名", "类型", "说明"], dim_rows)}

### 指标字段

{markdown_table(["指标", "字段名", "类型", "口径说明"], metric_rows)}

### 血缘思路

- ODS 从业务订单/支付/访问事件采集原始数据，按 `dt` 分区落表。
- DWD 对原始数据做状态过滤、字段标准化、金额单位统一和维度字段拉齐。
- DWS 按 `{grain}` 聚合，生成稳定可复用的主题汇总表。
- ADS 从 DWS 取数，补充报表需要的展示字段、排序字段和 {time_range}查询约束。

### 表复用判断

- 决策：{reuse_decision.get("decision", "未执行")}
- 推荐表：{reuse_table or "暂无"}
- 原因：{reuse_decision.get("reason", "未找到复用判断结果。")}

### 待人工确认

- 业务系统中无效订单、退款订单、取消订单是否计入指标。
- 地区和渠道是否以订单创建时快照为准，还是使用当前维表最新状态。
- 客单价等派生指标的小数精度和除零规则。
"""
    return {**state, "modeling_plan": plan}
