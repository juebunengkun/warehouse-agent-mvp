from __future__ import annotations


def _state() -> dict:
    return {
        "requirement": "Build a channel operation report and search DataHub for reusable certified tables.",
        "parsed": {
            "business_theme": "channel operation",
            "metrics": ["pay_amount", "refund_amount"],
            "dimensions": ["channel", "region"],
            "granularity": "stat_date + channel_id + region_id",
            "refresh_cycle": "T+1",
        },
        "agent_plan": {
            "tools_needed": [
                "search_tables",
                "search_datahub_assets",
                "get_datahub_dataset_schema",
                "get_datahub_lineage",
            ]
        },
    }


class FakeProvider:
    def search_dimensions(self, semantic_dimensions):
        return [{"name": "dim_channel_df"}]

    def search_facts(self, metrics, business_process=None):
        return [{"name": "dwd_sales_detail_di"}]

    def search_summaries(self, dimensions, metrics, grain=None, business_process=None):
        return [{"name": "dws_trade_channel_day_summary_di"}]

    def search_tables(self, **kwargs):
        return [{"name": "ads_channel_operation_daily_report_di"}]


def test_tool_router_calls_datahub_tools(monkeypatch):
    import dw_agent.nodes.tool_router as router

    urn = "urn:li:dataset:(urn:li:dataPlatform:hive,dws_trade_channel_day_summary_di,PROD)"
    monkeypatch.setattr(router, "get_metadata_provider", lambda config: FakeProvider())
    monkeypatch.setattr(
        router,
        "search_datahub_assets",
        lambda query, entity_types=None, limit=5: {
            "tool": "search_datahub_assets",
            "passed": True,
            "query": query,
            "assets": [{"urn": urn, "name": "dws_trade_channel_day_summary_di", "platform": "hive"}],
            "warnings": [],
            "errors": [],
        },
    )
    monkeypatch.setattr(
        router,
        "get_datahub_dataset_schema",
        lambda dataset_urn: {"tool": "get_datahub_dataset_schema", "passed": True, "fields": [{"name": "pay_amount"}]},
    )
    monkeypatch.setattr(
        router,
        "get_datahub_lineage",
        lambda dataset_urn, direction="upstream", depth=1: {
            "tool": "get_datahub_lineage",
            "passed": True,
            "lineage": [{"name": "dwd_sales_detail_di"}],
        },
    )
    monkeypatch.setattr(
        router,
        "get_datahub_ownership",
        lambda dataset_urn: {"tool": "get_datahub_ownership", "passed": True, "owners": [{"name": "trade-owner"}]},
    )
    monkeypatch.setattr(
        router,
        "get_datahub_tags_and_terms",
        lambda dataset_urn: {
            "tool": "get_datahub_tags_and_terms",
            "passed": True,
            "tags": ["Certified"],
            "glossary_terms": ["Trade"],
        },
    )

    result = router.tool_router(_state())

    planned_tools = [item["tool"] for item in result["tool_calls"]]
    assert "search_datahub_assets" in planned_tools
    assert "get_datahub_dataset_schema" in planned_tools
    assert result["tool_results"]["search_datahub_assets"]["assets"][0]["name"] == "dws_trade_channel_day_summary_di"
    assert result["tool_results"]["datahub_dataset_context"][0]["ownership"]["owners"][0]["name"] == "trade-owner"
    assert not result["tool_errors"]


def test_tool_router_records_datahub_skipped_when_disabled(monkeypatch):
    import dw_agent.nodes.tool_router as router

    monkeypatch.setenv("DATAHUB_MCP_ENABLED", "false")
    monkeypatch.delenv("DATAHUB_GMS_TOKEN", raising=False)
    monkeypatch.setattr(router, "get_metadata_provider", lambda config: FakeProvider())

    result = router.tool_router(_state())

    assert result["tool_results"]["search_datahub_assets"]["skipped"] is True
    assert result["tool_results"]["datahub_dataset_context"] == []
    assert not result["tool_errors"]
