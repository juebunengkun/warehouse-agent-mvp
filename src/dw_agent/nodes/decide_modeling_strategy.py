from __future__ import annotations

from typing import Any

from dw_agent.metadata import find_tables_by_names, load_table_metadata, table_suffix
from dw_agent.nodes.common import table_names
from dw_agent.nodes.decide_table_reuse import infer_business_process
from dw_agent.state import AgentState

DIMENSION_TABLE_RULES = {
    "渠道": "dim_channel_df",
    "渠道类型": "dim_channel_df",
    "地区": "dim_region_df",
    "省份": "dim_region_df",
    "城市": "dim_region_df",
    "新老用户": "dim_user_profile_df",
    "会员等级": "dim_user_profile_df",
}

TRADE_METRICS = {
    "销售额",
    "订单数",
    "支付订单数",
    "支付用户数",
    "GMV",
    "实付金额",
    "优惠金额",
    "退款金额",
    "客单价",
    "ARPU",
}
TRAFFIC_METRICS = {"曝光UV", "点击UV", "支付转化率"}


def decide_modeling_strategy(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    kb_path = state.get("knowledge_base_path")
    metadata = load_table_metadata(kb_path)
    metadata_by_name = {table["name"]: table for table in metadata}
    names = table_names(parsed)
    business_process = infer_business_process(parsed)
    reuse_decision = state.get("reuse_decision", {})

    fact_names = _fact_table_names(parsed)
    dim_names = _dimension_table_names(parsed)
    summary_names = (
        [reuse_decision["table"]] if reuse_decision.get("decision") == "reuse_existing_dws" else [names["dws"]]
    )
    app_names = _application_table_names(parsed, metadata_by_name, names)

    fact_tables = [_table_entry(table, _reason_for_table(table)) for table in find_tables_by_names(fact_names, kb_path)]
    dim_tables = [_table_entry(table, _reason_for_table(table)) for table in find_tables_by_names(dim_names, kb_path)]
    summary_tables = [
        {
            **_table_entry(table, _summary_reason(table, reuse_decision)),
            "reuse": table.get("name") == reuse_decision.get("table"),
        }
        for table in find_tables_by_names(summary_names, kb_path)
    ]
    if not summary_tables and summary_names:
        summary_tables = [_planned_entry(summary_names[0], "DWS", "summary_fact", parsed.get("granularity", "待确认"))]

    application_tables = [
        _table_entry(table, "面向 BI 看板消费，按日刷新。") for table in find_tables_by_names(app_names, kb_path)
    ]
    if not application_tables:
        application_tables = [
            _planned_entry(names["ads"], "ADS", "application_report", parsed.get("granularity", "待确认"))
        ]

    join_plan = _build_join_plan(fact_tables, dim_tables, metadata_by_name)
    dependency_plan = _build_dependency_plan(dim_tables, fact_tables, summary_tables, application_tables)
    risk_notes = [
        "复用 DWS 前需要确认粒度和指标口径一致。",
        "事实表关联维表必须防止一对多 join 导致指标膨胀。",
    ]
    if reuse_decision.get("risk_notes"):
        risk_notes.extend(reuse_decision["risk_notes"])

    strategy = {
        "business_process": business_process,
        "fact_tables": fact_tables,
        "dim_tables": dim_tables,
        "summary_tables": summary_tables,
        "application_tables": application_tables,
        "join_plan": join_plan,
        "dependency_plan": dependency_plan,
        "reuse_mode": reuse_decision.get("decision") == "reuse_existing_dws",
        "risk_notes": risk_notes,
    }

    trace = [
        *state.get("tool_trace", []),
        {
            "tool": "modeling_strategy",
            "input": {
                "business_process": business_process,
                "dimensions": parsed.get("dimensions", []),
                "metrics": parsed.get("metrics", []),
            },
            "output": {
                "fact_tables": [table["name"] for table in fact_tables],
                "dim_tables": [table["name"] for table in dim_tables],
                "summary_tables": [table["name"] for table in summary_tables],
                "application_tables": [table["name"] for table in application_tables],
            },
        },
    ]
    return {**state, "modeling_strategy": strategy, "tool_trace": trace}


def _fact_table_names(parsed: dict[str, Any]) -> list[str]:
    metrics = set(parsed.get("metrics", []))
    table_names = []
    if metrics & TRADE_METRICS:
        table_names.append("dwd_sales_detail_di")
    if metrics & TRAFFIC_METRICS:
        table_names.append("dwd_user_visit_log_di")
    return table_names or ["dwd_sales_detail_di"]


def _dimension_table_names(parsed: dict[str, Any]) -> list[str]:
    names = []
    for dimension in parsed.get("dimensions", []):
        table_name = DIMENSION_TABLE_RULES.get(dimension)
        if table_name and table_name not in names:
            names.append(table_name)
    return names


def _application_table_names(
    parsed: dict[str, Any], metadata_by_name: dict[str, dict[str, Any]], names: dict[str, str]
) -> list[str]:
    if (
        infer_business_process(parsed) == "channel_operation"
        and "ads_channel_operation_daily_report_di" in metadata_by_name
    ):
        return ["ads_channel_operation_daily_report_di"]
    return [names["ads"]]


def _table_entry(table: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "name": table.get("name"),
        "layer": table.get("layer"),
        "table_type": table.get("table_type", ""),
        "grain": table.get("grain", ""),
        "primary_keys": table.get("primary_keys", []),
        "foreign_keys": table.get("foreign_keys", []),
        "update_mode": table.get("update_mode", ""),
        "suffix": table_suffix(table.get("name", "")),
        "partition_key": table.get("partition_key", ""),
        "owner": table.get("owner", ""),
        "sla_time": table.get("sla_time", ""),
        "certified": table.get("certified", False),
        "description": table.get("description", ""),
        "reason": reason,
    }


def _planned_entry(name: str, layer: str, table_type: str, grain: str) -> dict[str, Any]:
    return {
        "name": name,
        "layer": layer,
        "table_type": table_type,
        "grain": grain,
        "primary_keys": [],
        "foreign_keys": [],
        "update_mode": "incremental",
        "suffix": table_suffix(name),
        "partition_key": "dt",
        "owner": "report_data",
        "sla_time": "08:30",
        "certified": False,
        "description": "根据当前报表需求规划的新表。",
        "reason": "未找到完全可复用表，按报表粒度规划新表。",
    }


def _reason_for_table(table: dict[str, Any]) -> str:
    table_type = table.get("table_type")
    update_mode = table.get("update_mode")
    if table_type == "transaction_fact":
        return f"{table.get('description')} 事件事实表适合按 dt 增量产出。"
    if table_type == "dimension":
        return f"{table.get('description')} 低频变化维度适合 {update_mode}。"
    return table.get("description", "")


def _summary_reason(table: dict[str, Any], reuse_decision: dict[str, Any]) -> str:
    if table.get("name") == reuse_decision.get("table"):
        return "已有认证 DWS 覆盖所需维度和指标，优先复用。"
    return "按报表粒度沉淀公共汇总指标。"


def _build_join_plan(
    fact_tables: list[dict[str, Any]],
    dim_tables: list[dict[str, Any]],
    metadata_by_name: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    dim_names = {table["name"] for table in dim_tables}
    joins = []
    for fact in fact_tables:
        source = metadata_by_name.get(fact["name"], {})
        for foreign_key in source.get("foreign_keys", []):
            ref_table = foreign_key.get("ref_table")
            if ref_table not in dim_names:
                continue
            join_key = foreign_key.get("field", "")
            joins.append(
                {
                    "left_table": fact["name"],
                    "right_table": ref_table,
                    "join_type": foreign_key.get("join_type", "left_join"),
                    "join_keys": [join_key] if join_key else [],
                    "partition_condition": f"{ref_table}.dt='${{bizdate}}'",
                    "risk": f"如果维表 {ref_table}.{foreign_key.get('ref_field')} 不唯一，会导致指标膨胀。",
                }
            )
    return joins


def _build_dependency_plan(
    dim_tables: list[dict[str, Any]],
    fact_tables: list[dict[str, Any]],
    summary_tables: list[dict[str, Any]],
    application_tables: list[dict[str, Any]],
) -> list[str]:
    ordered_tables = [*dim_tables, *fact_tables, *summary_tables, *application_tables]
    return [f"{table['name']} {table.get('partition_key') or 'dt'}=${{bizdate}}" for table in ordered_tables]
