from __future__ import annotations


def test_parse_requirement_does_not_treat_pay_user_metric_as_user_dimension(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")

    from dw_agent.nodes.parse_requirement import parse_requirement

    state = parse_requirement(
        {
            "requirement": "做一个销售日报，按天、地区、渠道统计销售额、订单数、支付用户数和客单价。",
            "knowledge_base_path": "knowledge_base",
        }
    )

    parsed = state["parsed"]
    assert parsed["metrics"] == ["销售额", "订单数", "支付用户数", "客单价"]
    assert parsed["dimensions"] == ["日期", "地区", "渠道"]
    assert parsed["granularity"] == "日期-地区-渠道"
    assert parsed["parser_source"] == "rules"
