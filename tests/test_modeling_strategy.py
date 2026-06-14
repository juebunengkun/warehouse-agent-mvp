from __future__ import annotations

import json
from pathlib import Path


def _run_complex_case(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")

    from dw_agent.graph import run_agent

    project_root = Path(__file__).resolve().parents[1]
    requirement = (project_root / "examples" / "sales_channel_daily.md").read_text(encoding="utf-8")
    return run_agent(requirement)


def test_modeling_strategy_contains_dim_tables(monkeypatch):
    result = _run_complex_case(monkeypatch)
    dim_names = {table["name"] for table in result["modeling_strategy"]["dim_tables"]}

    assert {"dim_channel_df", "dim_region_df", "dim_user_profile_df"}.issubset(dim_names)


def test_modeling_strategy_update_modes(monkeypatch):
    result = _run_complex_case(monkeypatch)
    strategy = result["modeling_strategy"]
    fact = next(table for table in strategy["fact_tables"] if table["name"] == "dwd_sales_detail_di")
    dim = next(table for table in strategy["dim_tables"] if table["name"] == "dim_channel_df")

    assert fact["update_mode"] == "incremental"
    assert fact["suffix"] == "_di"
    assert dim["update_mode"] == "full_snapshot"
    assert dim["suffix"] == "_df"


def test_modeling_strategy_join_plan(monkeypatch):
    result = _run_complex_case(monkeypatch)
    join_plan = result["modeling_strategy"]["join_plan"]

    assert any(
        item["left_table"] == "dwd_sales_detail_di"
        and item["right_table"] == "dim_channel_df"
        and item["join_type"] == "left_join"
        and item["join_keys"] == ["channel_id"]
        and item["partition_condition"] == "dim_channel_df.dt='${bizdate}'"
        for item in join_plan
    )


def test_reuse_decision_checks_grain_and_fields(monkeypatch):
    result = _run_complex_case(monkeypatch)
    reuse_decision = result["reuse_decision"]

    assert reuse_decision["decision"] == "reuse_existing_dws"
    assert reuse_decision["table"] == "dws_trade_channel_day_summary_di"
    assert reuse_decision["hard_checks"]["grain_matched"] is True
    assert reuse_decision["hard_checks"]["field_covered"] is True


def test_sales_channel_daily_still_runs(monkeypatch):
    result = _run_complex_case(monkeypatch)

    assert result["sql_validation"]["passed"] is True
    assert result["sql_style_review"]["passed"] is True
    assert "dim_channel_df" in result["final_report"]
    assert "SQL Style Review" in result["final_report"]


def test_reuse_existing_dws_generates_ads_only(monkeypatch):
    result = _run_complex_case(monkeypatch)

    assert "CREATE TABLE IF NOT EXISTS dws_trade_channel_day_summary_di" not in result["ddl"]
    assert "INSERT OVERWRITE TABLE dws_trade_channel_day_summary_di" not in result["etl_sql"]
    assert "INSERT OVERWRITE TABLE ads_channel_operation_daily_report_di" in result["etl_sql"]


def test_modeling_strategy_no_hardcoded_table_names(tmp_path):
    from dw_agent.metadata import LocalJsonMetadataProvider
    from dw_agent.nodes.common import DIMENSION_COLUMNS, METRIC_COLUMNS
    from dw_agent.nodes.decide_modeling_strategy import decide_modeling_strategy

    provider = LocalJsonMetadataProvider("knowledge_base")
    tables = provider.list_tables()
    renamed_table = "dim_mock_channel_snapshot_df"
    for table in tables:
        if table["name"] == "dim_channel_df":
            table["name"] = renamed_table

    (tmp_path / "table_metadata.json").write_text(json.dumps({"tables": tables}, ensure_ascii=False), encoding="utf-8")

    state = {
        "knowledge_base_path": str(tmp_path),
        "parsed": {
            "business_theme": "metadata selection",
            "metrics": [_metric_for_field(METRIC_COLUMNS, "sales_amount")],
            "dimensions": [
                _dimension_for_field(DIMENSION_COLUMNS, "stat_date"),
                _dimension_for_field(DIMENSION_COLUMNS, "channel_id"),
            ],
            "granularity": "stat_date-channel",
            "refresh_cycle": "T+1",
        },
        "reuse_decision": {"decision": "create_new_tables"},
    }

    result = decide_modeling_strategy(state)
    dim_names = {table["name"] for table in result["modeling_strategy"]["dim_tables"]}
    join_right_tables = {item["right_table"] for item in result["modeling_strategy"]["join_plan"]}

    assert renamed_table in dim_names
    assert "dim_channel_df" not in dim_names
    assert renamed_table in join_right_tables


def test_modeling_strategy_selects_fact_by_metrics():
    from dw_agent.nodes.common import DIMENSION_COLUMNS, METRIC_COLUMNS
    from dw_agent.nodes.decide_modeling_strategy import decide_modeling_strategy

    state = {
        "knowledge_base_path": "knowledge_base",
        "parsed": {
            "business_theme": "metadata selection",
            "metrics": [_metric_for_field(METRIC_COLUMNS, "sales_amount")],
            "dimensions": [_dimension_for_field(DIMENSION_COLUMNS, "stat_date")],
            "granularity": "stat_date",
            "refresh_cycle": "T+1",
        },
        "reuse_decision": {"decision": "create_new_tables"},
    }

    result = decide_modeling_strategy(state)
    fact_tables = result["modeling_strategy"]["fact_tables"]

    assert fact_tables
    assert fact_tables[0]["table_type"] == "transaction_fact"
    assert any(field["name"] == "pay_amount" for field in fact_tables[0]["fields"])


def test_modeling_strategy_selects_dim_by_metadata():
    from dw_agent.nodes.common import DIMENSION_COLUMNS, METRIC_COLUMNS
    from dw_agent.nodes.decide_modeling_strategy import decide_modeling_strategy

    state = {
        "knowledge_base_path": "knowledge_base",
        "parsed": {
            "business_theme": "metadata selection",
            "metrics": [_metric_for_field(METRIC_COLUMNS, "sales_amount")],
            "dimensions": [_dimension_for_field(DIMENSION_COLUMNS, "channel_id")],
            "granularity": "channel",
            "refresh_cycle": "T+1",
        },
        "reuse_decision": {"decision": "create_new_tables"},
    }

    result = decide_modeling_strategy(state)
    dim_tables = result["modeling_strategy"]["dim_tables"]

    assert dim_tables
    assert dim_tables[0]["layer"] == "DIM"
    assert dim_tables[0]["table_type"] == "dimension"
    assert dim_tables[0]["certified"] is True
    assert any(field["name"] == "channel_id" for field in dim_tables[0]["fields"])


def test_reuse_decision_hard_checks(monkeypatch):
    result = _run_complex_case(monkeypatch)
    hard_checks = result["reuse_decision"]["hard_checks"]

    assert set(hard_checks) >= {
        "field_covered",
        "grain_matched",
        "metric_semantics_matched",
        "business_process_matched",
        "partition_available",
        "certified",
        "sla_satisfied",
    }


def test_generate_ddl_uses_metadata_fields():
    from dw_agent.nodes.generate_ddl import generate_ddl

    state = {
        "parsed": {"metrics": [], "dimensions": []},
        "modeling_strategy": {
            "dim_tables": [],
            "fact_tables": [],
            "summary_tables": [],
            "application_tables": [
                {
                    "name": "ads_custom_report_di",
                    "layer": "ADS",
                    "table_type": "application_report",
                    "partition_key": "dt",
                    "fields": [
                        {"name": "custom_dim", "type": "STRING", "comment": "custom dimension"},
                        {"name": "custom_metric", "type": "BIGINT", "comment": "custom metric"},
                        {"name": "dt", "type": "STRING", "comment": "partition"},
                    ],
                }
            ],
        },
    }

    result = generate_ddl(state)

    assert "custom_metric BIGINT" in result["ddl"]
    assert "sales_amount" not in result["ddl"]


def test_generate_etl_uses_join_plan():
    from dw_agent.nodes.common import DIMENSION_COLUMNS, METRIC_COLUMNS
    from dw_agent.nodes.generate_etl import generate_etl

    channel_dimension = _dimension_for_field(DIMENSION_COLUMNS, "channel_id")
    state = {
        "parsed": {
            "metrics": [_metric_for_field(METRIC_COLUMNS, "sales_amount")],
            "dimensions": [_dimension_for_field(DIMENSION_COLUMNS, "stat_date"), channel_dimension],
            "granularity": "stat_date-channel",
            "refresh_cycle": "T+1",
        },
        "reuse_decision": {"decision": "create_new_tables"},
        "modeling_strategy": {
            "source_tables": [
                {
                    "name": "ods_custom_event_di",
                    "partition_key": "dt",
                    "fields": [
                        {"name": "event_time", "type": "STRING"},
                        {"name": "channel_id", "type": "STRING"},
                        {"name": "pay_amount", "type": "DECIMAL(18,2)"},
                        {"name": "order_status", "type": "STRING"},
                    ],
                }
            ],
            "fact_tables": [
                {
                    "name": "dwd_custom_fact_di",
                    "partition_key": "dt",
                    "fields": [
                        {"name": "stat_date", "type": "STRING"},
                        {"name": "channel_id", "type": "STRING"},
                        {"name": "pay_amount", "type": "DECIMAL(18,2)"},
                        {"name": "order_status", "type": "STRING"},
                    ],
                }
            ],
            "summary_tables": [{"name": "dws_custom_summary_di", "reuse": False, "partition_key": "dt"}],
            "application_tables": [{"name": "ads_custom_report_di", "partition_key": "dt"}],
            "join_plan": [
                {
                    "right_table": "dim_custom_channel_df",
                    "join_keys": ["channel_id"],
                    "right_keys": ["channel_id"],
                    "partition_condition": "dim_custom_channel_df.dt='${bizdate}'",
                }
            ],
        },
    }

    result = generate_etl(state)

    assert "LEFT JOIN dim_custom_channel_df" in result["etl_sql"]
    assert "dwd.channel_id = dim_custom_channel_df.channel_id" in result["etl_sql"]
    assert "dim_custom_channel_df.dt='${bizdate}'" in result["etl_sql"]


def _dimension_for_field(dimensions: dict, field_name: str) -> str:
    for dimension, fields in dimensions.items():
        if any(field[0] == field_name for field in fields):
            return dimension
    raise AssertionError(f"missing dimension for field {field_name}")


def _metric_for_field(metrics: dict, field_name: str) -> str:
    for metric, field in metrics.items():
        if field[0] == field_name:
            return metric
    raise AssertionError(f"missing metric for field {field_name}")
