from __future__ import annotations

from dw_agent.nodes.common import group_fields, metric_columns, metric_expression, table_names
from dw_agent.state import AgentState


def generate_etl(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    names = table_names(parsed)
    strategy = state.get("modeling_strategy", {})
    reuse_decision = state.get("reuse_decision", {})
    reuse_dws = reuse_decision.get("decision") == "reuse_existing_dws"
    dws_source_table = str(reuse_decision.get("table") or names["dws"]) if reuse_dws else names["dws"]
    ads_table = _ads_table_name(strategy, names["ads"])

    group_by = group_fields(parsed)
    metric_fields = [(metric, field) for metric, field, _, _ in metric_columns(parsed.get("metrics", []))]

    sections = [_dwd_insert(names["ods"], names["dwd"])]
    if reuse_dws:
        sections.append(f"""-- 2. DWD -> DWS：复用已有汇总层
-- 目标粒度：{_grain(strategy.get("summary_tables", []), parsed.get("granularity", "待确认"))}
-- 已找到可复用 DWS 表 {dws_source_table}，当前报表不重复生成 DWS。""")
    else:
        sections.append(_dws_insert(names["dwd"], names["dws"], group_by, metric_fields, strategy))
    sections.append(_ads_insert(dws_source_table, ads_table, group_by, metric_fields, strategy))

    etl = "-- 参数：${bizdate}，格式 yyyy-MM-dd\n\n" + "\n\n".join(sections) + "\n"
    return {**state, "etl_sql": etl}


def _dwd_insert(ods_table: str, dwd_table: str) -> str:
    dwd_select_fields = [
        "order_id",
        "user_id",
        "sku_id",
        "CAST(gmv_amount AS DECIMAL(18,2)) AS gmv_amount",
        "CAST(pay_amount AS DECIMAL(18,2)) AS pay_amount",
        "CAST(discount_amount AS DECIMAL(18,2)) AS discount_amount",
        "CAST(refund_amount AS DECIMAL(18,2)) AS refund_amount",
        "order_status",
        "exposure_user_id",
        "click_user_id",
        "order_user_id",
        "channel_id",
        "channel_name",
        "channel_type",
        "region_id",
        "region_name",
        "province_name",
        "city_name",
        "user_type",
        "member_level",
        "event_time AS pay_time",
        "SUBSTR(event_time, 1, 10) AS stat_date",
    ]
    select_fields = ",\n  ".join(dwd_select_fields)
    return f"""-- 1. ODS -> DWD：目标粒度 order_id / event_id
INSERT OVERWRITE TABLE {dwd_table} PARTITION (dt='${{bizdate}}')
SELECT
  {select_fields}
FROM {ods_table}
WHERE dt = '${{bizdate}}'
  AND is_valid = 1;"""


def _dws_insert(
    dwd_table: str,
    dws_table: str,
    group_by: list[str],
    metric_fields: list[tuple[str, str]],
    strategy: dict,
) -> str:
    metric_select_fields = [_metric_select(metric, field) for metric, field in metric_fields]
    dws_select_fields = [*group_by, *metric_select_fields]
    select_fields = ",\n  ".join(dws_select_fields)
    group_by_expr = ", ".join(group_by)
    joins = _dim_joins(strategy)
    return f"""-- 2. DWD -> DWS：目标粒度 {group_by_expr}
INSERT OVERWRITE TABLE {dws_table} PARTITION (dt='${{bizdate}}')
SELECT
  {select_fields}
FROM {dwd_table} dwd
{joins}
WHERE dwd.dt = '${{bizdate}}'
GROUP BY {group_by_expr};"""


def _ads_insert(
    dws_source_table: str,
    ads_table: str,
    group_by: list[str],
    metric_fields: list[tuple[str, str]],
    strategy: dict,
) -> str:
    ads_select_fields = [*group_by, *[field for _, field in metric_fields], "CURRENT_TIMESTAMP() AS update_time"]
    select_fields = ",\n  ".join(ads_select_fields)
    group_by_expr = ", ".join(group_by)
    return f"""-- 3. DWS -> ADS：目标粒度 {_grain(strategy.get("application_tables", []), group_by_expr)}
INSERT OVERWRITE TABLE {ads_table} PARTITION (dt='${{bizdate}}')
SELECT
  {select_fields}
FROM {dws_source_table}
WHERE dt = '${{bizdate}}';"""


def _metric_select(metric: str, field: str) -> str:
    expression = metric_expression(metric)
    if field.endswith("_amount") or field in {"avg_order_amount", "arpu"}:
        return f"CAST({expression} AS DECIMAL(18,2)) AS {field}"
    return f"{expression} AS {field}"


def _dim_joins(strategy: dict) -> str:
    joins = []
    for item in strategy.get("join_plan", []):
        right_table = item.get("right_table")
        join_keys = item.get("join_keys", [])
        if not right_table or not join_keys:
            continue
        conditions = [f"dwd.{key} = {right_table}.{key}" for key in join_keys]
        conditions.append(item.get("partition_condition", f"{right_table}.dt='${{bizdate}}'"))
        joins.append(f"LEFT JOIN {right_table}\n  ON " + "\n  AND ".join(conditions))
    return "\n".join(joins)


def _grain(tables: list[dict], fallback: str) -> str:
    if tables:
        return tables[0].get("grain") or fallback
    return fallback


def _ads_table_name(strategy: dict, fallback: str) -> str:
    app_tables = strategy.get("application_tables", [])
    if app_tables:
        return app_tables[0].get("name", fallback)
    return fallback
