from __future__ import annotations


def test_graph_stops_for_confirmation(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")

    from dw_agent.graph import run_agent

    result = run_agent("做一个销售日报，按天、地区、渠道统计销售额和订单数，T+1 刷新。", require_confirmation=True)

    assert result["agent_decision"] == "awaiting_user_confirmation"
    assert result["clarification_questions"]
    assert "retrievals" not in result
    assert "ddl" not in result


def test_graph_generates_after_human_confirmation(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")

    from dw_agent.graph import run_agent

    draft = run_agent("做一个销售日报，按天、地区、渠道统计销售额和订单数，T+1 刷新。", require_confirmation=True)
    result = run_agent("做一个销售日报，按天、地区、渠道统计销售额和订单数，T+1 刷新。", approved_parsed=draft["parsed"])

    assert result["agent_decision"] == "continue_generation"
    assert result["sql_validation"]["passed"] is True
    assert result["tool_trace"]
    assert "CREATE TABLE" in result["ddl"]
