from __future__ import annotations


def test_sqlglot_detects_select_field_missing_from_group_by(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")

    from dw_agent.tools import sql_validation_tool

    parsed = {
        "metrics": ["销售额"],
        "dimensions": ["日期", "地区"],
        "granularity": "日期-地区",
        "refresh_cycle": "T+1 日刷新",
    }
    ddl = """
CREATE TABLE IF NOT EXISTS dws_sales_day_summary_di (
  stat_date STRING,
  region_id STRING,
  sales_amount DECIMAL(18,2)
)
PARTITIONED BY (dt STRING)
STORED AS ORC;
"""
    etl = """
INSERT OVERWRITE TABLE dwd_sales_detail_di PARTITION (dt='${bizdate}')
SELECT order_id, user_id, pay_amount, region_id, SUBSTR(event_time, 1, 10) AS stat_date
FROM ods_sales_event_di
WHERE dt = '${bizdate}';

INSERT OVERWRITE TABLE dws_sales_day_summary_di PARTITION (dt='${bizdate}')
SELECT stat_date, region_id, SUM(pay_amount) AS sales_amount
FROM dwd_sales_detail_di
WHERE dt = '${bizdate}'
GROUP BY stat_date;

INSERT OVERWRITE TABLE ads_sales_report_di PARTITION (dt='${bizdate}')
SELECT stat_date, region_id, sales_amount
FROM dws_sales_day_summary_di
WHERE dt = '${bizdate}';
"""

    validation, _ = sql_validation_tool(ddl, etl, parsed)

    assert validation["passed"] is False
    assert any("非聚合字段" in error or "GROUP BY" in error for error in validation["errors"])
