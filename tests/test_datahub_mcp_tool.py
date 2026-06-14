from __future__ import annotations

from dw_agent.tools.datahub_mcp_client import DataHubMcpClient
from dw_agent.tools.datahub_mcp_tool import (
    get_datahub_dataset_schema,
    get_datahub_lineage,
    get_datahub_ownership,
    get_datahub_tags_and_terms,
    search_datahub_assets,
)


def test_search_datahub_assets_uses_mocked_official_search_tool():
    client = DataHubMcpClient(
        mock_responses={
            "search": {
                "passed": True,
                "entities": [
                    {
                        "urn": "urn:li:dataset:(urn:li:dataPlatform:hive,dws_trade_channel_day_summary_di,PROD)",
                        "name": "dws_trade_channel_day_summary_di",
                        "platform": "hive",
                        "owners": [{"name": "analytics-platform"}],
                        "tags": [{"name": "Certified"}],
                        "score": 0.92,
                    }
                ],
            }
        }
    )

    result = search_datahub_assets("channel operation certified dws", client=client)

    assert result["passed"] is True
    assert result["assets"][0]["name"] == "dws_trade_channel_day_summary_di"
    assert result["assets"][0]["owner"] == "analytics-platform"
    assert result["assets"][0]["tags"] == ["Certified"]


def test_datahub_schema_lineage_ownership_and_tags_are_normalized():
    urn = "urn:li:dataset:(urn:li:dataPlatform:hive,dws_trade_channel_day_summary_di,PROD)"
    client = DataHubMcpClient(
        mock_responses={
            "list_schema_fields": {
                "fields": [
                    {"fieldPath": "stat_date", "nativeDataType": "string", "description": "Report date"},
                    {"fieldPath": "pay_amount", "nativeDataType": "decimal(18,2)", "nullable": False},
                ]
            },
            "get_lineage": {
                "entities": [{"urn": "urn:li:dataset:(urn:li:dataPlatform:hive,dwd_sales_detail_di,PROD)"}]
            },
            "get_entities": {
                "entities": [
                    {
                        "urn": urn,
                        "owners": [{"name": "trade-data-owner", "type": "DATAOWNER"}],
                        "tags": [{"name": "Certified"}],
                        "glossaryTerms": [{"name": "Trade"}],
                        "domain": "Commerce",
                        "dataProduct": "Channel Operations",
                    }
                ]
            },
        }
    )

    schema = get_datahub_dataset_schema(urn, client=client)
    lineage = get_datahub_lineage(urn, client=client)
    ownership = get_datahub_ownership(urn, client=client)
    tags_terms = get_datahub_tags_and_terms(urn, client=client)

    assert schema["fields"][0]["name"] == "stat_date"
    assert schema["fields"][1]["nullable"] is False
    assert lineage["lineage"][0]["name"] == "dwd_sales_detail_di"
    assert ownership["owners"][0]["name"] == "trade-data-owner"
    assert tags_terms["tags"] == ["Certified"]
    assert tags_terms["glossary_terms"] == ["Trade"]
    assert tags_terms["data_product"] == "Channel Operations"


def test_datahub_tool_returns_skipped_when_disabled():
    result = search_datahub_assets("anything", client=DataHubMcpClient(enabled=False))

    assert result["skipped"] is True
    assert result["errors"] == []
    assert "disabled" in result["warnings"][0].lower()
