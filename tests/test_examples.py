from __future__ import annotations

from pathlib import Path


def test_complex_channel_daily_example_reuses_existing_dws(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")

    from dw_agent.graph import run_agent

    project_root = Path(__file__).resolve().parents[1]
    requirement = (project_root / "examples" / "sales_channel_daily.md").read_text(encoding="utf-8")

    result = run_agent(requirement)
    parsed = result["parsed"]

    assert {"曝光UV", "点击UV", "下单用户数", "支付用户数", "支付订单数", "GMV", "实付金额", "退款金额"}.issubset(
        set(parsed["metrics"])
    )
    assert {"日期", "渠道", "渠道类型", "省份", "城市", "新老用户", "会员等级"}.issubset(set(parsed["dimensions"]))
    assert "用户" not in parsed["dimensions"]

    assert result["reuse_decision"]["decision"] == "reuse_existing_dws"
    assert result["reuse_decision"]["table"] == "dws_trade_channel_day_summary_di"
    assert result["sql_validation"]["passed"] is True
    assert result["sql_validation"]["sqlglot"]["etl_statement_count"] >= 2
