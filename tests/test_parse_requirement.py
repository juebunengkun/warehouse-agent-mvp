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


def test_parse_requirement_prefers_longest_metric_and_dimension_terms(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")

    from dw_agent.nodes.parse_requirement import parse_requirement

    state = parse_requirement(
        {
            "requirement": "做渠道日报，按日期、渠道、新老用户统计支付订单数、支付转化率和ARPU。",
            "knowledge_base_path": "knowledge_base",
        }
    )

    parsed = state["parsed"]
    assert parsed["metrics"] == ["支付订单数", "支付转化率", "ARPU"]
    assert parsed["dimensions"] == ["日期", "渠道", "新老用户"]
    assert "订单数" not in parsed["metrics"]
    assert "转化率" not in parsed["metrics"]
    assert "用户" not in parsed["dimensions"]


def test_parse_requirement_records_llm_failure_diagnostics(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class BrokenModel:
        def invoke(self, _prompt):
            raise PermissionError("blocked")

    import dw_agent.nodes.parse_requirement as parser

    monkeypatch.setattr(parser, "get_chat_model", lambda: BrokenModel())

    state = parser.parse_requirement(
        {
            "requirement": "做一个销售日报，按天、地区统计销售额。",
            "knowledge_base_path": "knowledge_base",
        }
    )

    assert state["parsed"]["parser_source"] == "rules_fallback_after_llm_error"
    assert state["llm_diagnostics"]["status"] == "failed"
    assert state["llm_diagnostics"]["error_type"] == "PermissionError"
