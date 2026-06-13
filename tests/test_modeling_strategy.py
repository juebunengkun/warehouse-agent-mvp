from __future__ import annotations

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
    assert "SQL 风格审查" in result["final_report"]


def test_reuse_existing_dws_generates_ads_only(monkeypatch):
    result = _run_complex_case(monkeypatch)

    assert "CREATE TABLE IF NOT EXISTS dws_trade_channel_day_summary_di" not in result["ddl"]
    assert "INSERT OVERWRITE TABLE dws_trade_channel_day_summary_di" not in result["etl_sql"]
    assert "INSERT OVERWRITE TABLE ads_channel_operation_daily_report_di" in result["etl_sql"]
