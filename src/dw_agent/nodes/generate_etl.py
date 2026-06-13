from __future__ import annotations

from typing import Any

from dw_agent.nodes.common import group_fields, metric_columns, metric_expression, table_names
from dw_agent.state import AgentState


def generate_etl(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    generated_names = table_names(parsed)
    strategy = state.get("modeling_strategy", {})
    reuse_decision = state.get("reuse_decision", {})
    reuse_dws = reuse_decision.get("decision") == "reuse_existing_dws"

    fact_tables = strategy.get("fact_tables", [])
    source_tables = strategy.get("source_tables", [])
    summary_table = _first_table_name(strategy.get("summary_tables", []), generated_names["dws"])
    dws_source_table = str(reuse_decision.get("table") or summary_table) if reuse_dws else summary_table
    ads_table = _first_table_name(strategy.get("application_tables", []), generated_names["ads"])
    group_by = group_fields(parsed)
    metric_fields = [(metric, field) for metric, field, _, _ in metric_columns(parsed.get("metrics", []))]

    sections: list[str] = []
    if fact_tables:
        for index, fact_table in enumerate(fact_tables, start=1):
            source_table = source_tables[min(index - 1, len(source_tables) - 1)] if source_tables else {}
            sections.append(_dwd_insert(source_table, fact_table, index))
    else:
        sections.append(_fallback_dwd_insert(generated_names["ods"], generated_names["dwd"]))

    if reuse_dws:
        sections.append(f"""-- DWD -> DWS: reuse existing summary table
-- Reused table: {dws_source_table}
-- Requested grain: {_grain(strategy.get("summary_tables", []), ", ".join(group_by))}
-- This report does not regenerate the reused DWS.""")
    else:
        sections.append(
            _dws_insert(
                _first_table_name(fact_tables, generated_names["dwd"]), summary_table, group_by, metric_fields, strategy
            )
        )

    sections.append(_ads_insert(dws_source_table, ads_table, group_by, metric_fields, strategy))

    etl = "-- Parameter: ${bizdate}, format yyyy-MM-dd\n\n" + "\n\n".join(sections) + "\n"
    return {**state, "etl_sql": etl}


def _dwd_insert(source_table: dict[str, Any], fact_table: dict[str, Any], index: int) -> str:
    source_name = str(source_table.get("name") or "ods_source_event_di")
    target_name = str(fact_table.get("name") or "dwd_generated_detail_di")
    partition_key = str(fact_table.get("partition_key") or "dt")
    target_fields = _non_partition_fields(fact_table)
    source_fields = {field.get("name") for field in source_table.get("fields", []) if field.get("name")}
    select_fields = ",\n  ".join(_source_expression(field, source_fields) for field in target_fields)
    filters = [f"src.{source_table.get('partition_key') or 'dt'} = '${{bizdate}}'"]
    if "is_valid" in source_fields:
        filters.append("src.is_valid = 1")
    where_clause = "\n  AND ".join(filters)
    return f"""-- {index}. ODS -> DWD: normalize provider-selected fact table
INSERT OVERWRITE TABLE {target_name} PARTITION ({partition_key}='${{bizdate}}')
SELECT
  {select_fields}
FROM {source_name} src
WHERE {where_clause};"""


def _fallback_dwd_insert(ods_table: str, dwd_table: str) -> str:
    return f"""-- 1. ODS -> DWD: fallback demo insert
INSERT OVERWRITE TABLE {dwd_table} PARTITION (dt='${{bizdate}}')
SELECT
  src.event_id AS event_id,
  SUBSTR(src.event_time, 1, 10) AS stat_date
FROM {ods_table} src
WHERE src.dt = '${{bizdate}}';"""


def _dws_insert(
    dwd_table: str,
    dws_table: str,
    group_by: list[str],
    metric_fields: list[tuple[str, str]],
    strategy: dict[str, Any],
) -> str:
    metric_select_fields = [_metric_select(metric, field) for metric, field in metric_fields]
    dws_select_fields = [*group_by, *metric_select_fields]
    select_fields = ",\n  ".join(dws_select_fields)
    group_by_expr = ", ".join(group_by)
    joins = _dim_joins(strategy)
    group_clause = f"GROUP BY {group_by_expr}" if group_by_expr else ""
    return f"""-- DWD -> DWS: aggregate at requested report grain
INSERT OVERWRITE TABLE {dws_table} PARTITION (dt='${{bizdate}}')
SELECT
  {select_fields}
FROM {dwd_table} dwd
{joins}
WHERE dwd.dt = '${{bizdate}}'
{group_clause};"""


def _ads_insert(
    dws_source_table: str,
    ads_table: str,
    group_by: list[str],
    metric_fields: list[tuple[str, str]],
    strategy: dict[str, Any],
) -> str:
    ads_select_fields = [*group_by, *[field for _, field in metric_fields], "CURRENT_TIMESTAMP() AS update_time"]
    select_fields = ",\n  ".join(ads_select_fields)
    return f"""-- DWS -> ADS: publish report-facing table
INSERT OVERWRITE TABLE {ads_table} PARTITION (dt='${{bizdate}}')
SELECT
  {select_fields}
FROM {dws_source_table}
WHERE dt = '${{bizdate}}';"""


def _non_partition_fields(table: dict[str, Any]) -> list[dict[str, Any]]:
    partition_key = table.get("partition_key") or "dt"
    fields = [field for field in table.get("fields", []) if field.get("name") and field.get("name") != partition_key]
    if fields:
        return fields
    return [
        {"name": "event_id", "type": "STRING", "comment": "source event id"},
        {"name": "stat_date", "type": "STRING", "comment": "stat date"},
    ]


def _source_expression(field: dict[str, Any], source_fields: set[str]) -> str:
    name = str(field.get("name"))
    sql_type = str(field.get("type") or "STRING")
    if name in source_fields:
        return _typed_source_column(name, sql_type)
    if name == "pay_time" and "event_time" in source_fields:
        return "src.event_time AS pay_time"
    if name == "stat_date" and "event_time" in source_fields:
        return "SUBSTR(src.event_time, 1, 10) AS stat_date"
    if sql_type.upper().startswith("DECIMAL"):
        return f"CAST(0 AS {sql_type}) AS {name}"
    if sql_type.upper() in {"BIGINT", "INT", "INTEGER", "TINYINT"}:
        return f"CAST(0 AS {sql_type}) AS {name}"
    return f"CAST(NULL AS {sql_type}) AS {name}"


def _typed_source_column(name: str, sql_type: str) -> str:
    if sql_type.upper().startswith("DECIMAL"):
        return f"CAST(src.{name} AS {sql_type}) AS {name}"
    return f"src.{name} AS {name}"


def _metric_select(metric: str, field: str) -> str:
    expression = metric_expression(metric)
    if field.endswith("_amount") or field in {"avg_order_amount", "arpu"}:
        return f"CAST({expression} AS DECIMAL(18,2)) AS {field}"
    if field.endswith("_rate"):
        return f"CAST({expression} AS DECIMAL(18,6)) AS {field}"
    return f"{expression} AS {field}"


def _dim_joins(strategy: dict[str, Any]) -> str:
    joins = []
    for item in strategy.get("join_plan", []):
        right_table = item.get("right_table")
        join_keys = item.get("join_keys", [])
        right_keys = item.get("right_keys", join_keys)
        if not right_table or not join_keys:
            continue
        conditions = []
        for left_key, right_key in zip(join_keys, right_keys, strict=False):
            conditions.append(f"dwd.{left_key} = {right_table}.{right_key}")
        conditions.append(item.get("partition_condition", f"{right_table}.dt='${{bizdate}}'"))
        joins.append(f"LEFT JOIN {right_table}\n  ON " + "\n  AND ".join(conditions))
    return "\n".join(joins)


def _grain(tables: list[dict[str, Any]], fallback: str) -> str:
    if tables:
        return tables[0].get("grain") or fallback
    return fallback


def _first_table_name(tables: list[dict[str, Any]], fallback: str) -> str:
    if tables:
        return str(tables[0].get("name") or fallback)
    return fallback
