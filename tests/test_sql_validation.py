from __future__ import annotations


def test_sql_validation_detects_missing_partition_and_group_by(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")

    from dw_agent.tools import sql_validation_tool

    parsed = {
        "metrics": ["销售额", "订单数"],
        "dimensions": ["日期", "地区", "渠道"],
        "granularity": "日期-地区-渠道",
        "refresh_cycle": "T+1 日刷新",
    }
    invalid_ddl = "CREATE TABLE bad_table (sales_amount DECIMAL(18,2));"
    invalid_etl = "INSERT OVERWRITE TABLE bad_table SELECT SUM(pay_amount) AS sales_amount FROM source_table;"

    validation, trace = sql_validation_tool(invalid_ddl, invalid_etl, parsed)

    assert validation["passed"] is False
    assert any("dt 分区" in error for error in validation["errors"])
    assert any("GROUP BY" in error for error in validation["errors"])
    assert trace["tool"] == "sql_validation"


def test_sql_validation_passes_generated_sql(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")

    from dw_agent.graph import run_agent

    result = run_agent("做一个销售日报，按天、地区、渠道统计销售额和订单数，T+1 刷新。")

    assert result["sql_validation"]["passed"] is True
    assert result["sql_validation"]["errors"] == []
