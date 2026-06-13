from __future__ import annotations

from dw_agent.nodes.common import group_fields, metric_expression, metric_columns, table_names
from dw_agent.state import AgentState


def generate_etl(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    names = table_names(parsed)
    reuse_decision = state.get("reuse_decision", {})
    dws_source_table = reuse_decision.get("table") if reuse_decision.get("decision") == "reuse_existing_dws" else names["dws"]
    metrics = parsed.get("metrics", [])
    group_by = group_fields(parsed)
    metric_fields = [(metric, field) for metric, field, _, _ in metric_columns(metrics)]

    dwd_select_fields = [
        "order_id",
        "user_id",
        "sku_id",
        "pay_amount",
        "order_status",
        "channel_id",
        "channel_name",
        "region_id",
        "region_name",
        "event_time AS pay_time",
        "SUBSTR(event_time, 1, 10) AS stat_date",
    ]

    dws_select_fields = [*group_by]
    dws_select_fields.extend([f"{metric_expression(metric)} AS {field}" for metric, field in metric_fields])

    ads_select_fields = [*group_by, *[field for _, field in metric_fields], "CURRENT_TIMESTAMP() AS update_time"]

    if reuse_decision.get("decision") == "reuse_existing_dws":
        dws_step = f"""-- 2. DWD -> DWS：复用已有汇总层
-- 已找到可复用 DWS 表 {dws_source_table}，当前报表不重复生成 DWS。
-- 如需重刷公共汇总层，请在上游公共任务中处理。"""
    else:
        dws_step = f"""-- 2. DWD -> DWS：按报表粒度聚合
INSERT OVERWRITE TABLE {names["dws"]} PARTITION (dt='${{bizdate}}')
SELECT
  {",\n  ".join(dws_select_fields)}
FROM {names["dwd"]}
WHERE dt = '${{bizdate}}'
GROUP BY {", ".join(group_by)};"""

    etl = f"""-- 参数：${{bizdate}}，格式 yyyy-MM-dd

-- 1. ODS -> DWD：清洗明细数据
INSERT OVERWRITE TABLE {names["dwd"]} PARTITION (dt='${{bizdate}}')
SELECT
  {",\n  ".join(dwd_select_fields)}
FROM {names["ods"]}
WHERE dt = '${{bizdate}}'
  AND is_valid = 1
  AND order_status IN ('PAID', 'FINISHED');

{dws_step}

-- 3. DWS -> ADS：生成报表结果表
INSERT OVERWRITE TABLE {names["ads"]} PARTITION (dt='${{bizdate}}')
SELECT
  {",\n  ".join(ads_select_fields)}
FROM {dws_source_table}
WHERE dt = '${{bizdate}}';
"""
    return {**state, "etl_sql": etl}
