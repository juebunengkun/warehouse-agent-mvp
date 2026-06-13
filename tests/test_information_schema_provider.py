from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _init_duckdb_demo(tmp_path: Path) -> Path:
    project_root = _project_root()
    script = project_root / "demo" / "init_duckdb_demo.py"
    db_path = tmp_path / "warehouse_demo.duckdb"
    env = {**os.environ, "WAREHOUSE_DUCKDB_PATH": str(db_path)}
    subprocess.run([sys.executable, str(script)], cwd=project_root, check=True, env=env)
    assert db_path.exists()
    return db_path


def test_information_schema_provider_duckdb_init(tmp_path):
    from dw_agent.metadata import InformationSchemaMetadataProvider

    db_path = _init_duckdb_demo(tmp_path)
    provider = InformationSchemaMetadataProvider({"db_type": "duckdb", "duckdb_path": str(db_path)})

    tables = provider.list_tables()

    assert tables
    assert any(table["source"] == "information_schema" for table in tables)


def test_information_schema_get_table_fields(tmp_path):
    from dw_agent.metadata import InformationSchemaMetadataProvider

    db_path = _init_duckdb_demo(tmp_path)
    provider = InformationSchemaMetadataProvider({"db_type": "duckdb", "duckdb_path": str(db_path)})

    table = provider.get_table("dwd_sales_detail_di")
    fields = {field["name"] for field in table["fields"]}

    assert table is not None
    assert {"order_id", "pay_amount", "dt"}.issubset(fields)


def test_semantic_mapper_from_information_schema(tmp_path):
    from dw_agent.metadata import InformationSchemaMetadataProvider

    db_path = _init_duckdb_demo(tmp_path)
    provider = InformationSchemaMetadataProvider({"db_type": "duckdb", "duckdb_path": str(db_path)})

    sales = provider.get_table("dwd_sales_detail_di")
    channel = provider.get_table("dim_channel_df")

    assert sales["layer"] == "DWD"
    assert sales["update_mode"] == "incremental"
    assert sales["table_type"] == "transaction_fact"
    assert channel["layer"] == "DIM"
    assert channel["update_mode"] == "full_snapshot"
    assert channel["table_type"] == "dimension"


def test_information_schema_search_dimensions(tmp_path):
    from dw_agent.metadata import InformationSchemaMetadataProvider

    db_path = _init_duckdb_demo(tmp_path)
    provider = InformationSchemaMetadataProvider({"db_type": "duckdb", "duckdb_path": str(db_path)})

    tables = provider.search_dimensions(["渠道", "商品类目", "新老用户"])
    field_sets = [{field["name"] for field in table["fields"]} for table in tables]

    assert any({"channel_id", "channel_name"}.issubset(fields) for fields in field_sets)
    assert any({"category_id", "category_level1_name"}.issubset(fields) for fields in field_sets)
    assert any({"user_id", "user_type", "member_level"}.issubset(fields) for fields in field_sets)
    assert all(table["table_type"] == "dimension" for table in tables)


def test_information_schema_search_facts(tmp_path):
    from dw_agent.metadata import InformationSchemaMetadataProvider

    db_path = _init_duckdb_demo(tmp_path)
    provider = InformationSchemaMetadataProvider({"db_type": "duckdb", "duckdb_path": str(db_path)})

    facts = provider.search_facts(["pay_amount", "refund_amount", "click_cnt", "exposure_cnt"], "category_operation")
    fact_names = {table["name"] for table in facts}

    assert "dwd_sales_detail_di" in fact_names
    assert "dwd_user_behavior_event_di" in fact_names


def test_information_schema_search_summaries(tmp_path):
    from dw_agent.metadata import InformationSchemaMetadataProvider

    db_path = _init_duckdb_demo(tmp_path)
    provider = InformationSchemaMetadataProvider({"db_type": "duckdb", "duckdb_path": str(db_path)})

    summaries = provider.search_summaries(
        ["日期", "商品类目", "渠道", "新老用户", "会员等级"],
        ["visit_user_cnt", "exposure_cnt", "click_cnt", "pay_amount", "refund_amount"],
        "stat_date + category_id + channel_id + user_type + member_level",
        "category_operation",
    )

    assert summaries
    assert summaries[0]["name"] == "dws_category_channel_day_summary_di"


def test_modeling_strategy_with_information_schema_provider(monkeypatch, tmp_path):
    from dw_agent.graph import run_agent

    db_path = _init_duckdb_demo(tmp_path)
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")
    monkeypatch.setenv("WAREHOUSE_METADATA_PROVIDER", "information_schema")
    monkeypatch.setenv("WAREHOUSE_DB_TYPE", "duckdb")
    monkeypatch.setenv("WAREHOUSE_DUCKDB_PATH", str(db_path))

    parsed = {
        "business_theme": "category operation",
        "metrics": ["visit_user_cnt", "exposure_cnt", "click_cnt", "pay_amount", "refund_amount"],
        "dimensions": ["日期", "商品类目", "渠道", "新老用户", "会员等级"],
        "granularity": "日期-商品类目-渠道-新老用户-会员等级",
        "refresh_cycle": "T+1",
        "time_range": "last 30 days",
        "data_layer_target": ["ODS", "DWD", "DWS", "ADS"],
        "sql_dialect": "Hive SQL",
        "assumptions": [],
        "parser_source": "approved_test",
    }

    result = run_agent("商品类目经营日报", approved_parsed=parsed)
    strategy = result["modeling_strategy"]

    assert strategy["business_process"] == "category_operation"
    assert strategy["dim_tables"]
    assert strategy["fact_tables"]
    assert any(table["name"] == "dws_category_channel_day_summary_di" for table in strategy["summary_tables"])
    assert any(table["name"] == "ads_category_operation_daily_report_di" for table in strategy["application_tables"])
    assert strategy["join_plan"]


def test_local_json_still_works(monkeypatch):
    from dw_agent.graph import run_agent

    monkeypatch.delenv("WAREHOUSE_METADATA_PROVIDER", raising=False)
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")

    requirement = (_project_root() / "examples" / "sales_channel_daily.md").read_text(encoding="utf-8")
    result = run_agent(requirement)

    assert result["sql_validation"]["passed"] is True


def test_sql_preview_select_only(tmp_path):
    from dw_agent.sql_preview import preview_duckdb_select

    db_path = _init_duckdb_demo(tmp_path)
    preview = preview_duckdb_select("SELECT channel_id FROM dim_channel_df", db_path=db_path)

    assert preview["columns"] == ["channel_id"]
    assert preview["row_count"] >= 1
    for bad_sql in ["DROP TABLE dim_channel_df", "INSERT INTO dim_channel_df VALUES ('x')"]:
        try:
            preview_duckdb_select(bad_sql, db_path=db_path)
        except ValueError:
            pass
        else:
            raise AssertionError(f"Unsafe SQL was not rejected: {bad_sql}")
