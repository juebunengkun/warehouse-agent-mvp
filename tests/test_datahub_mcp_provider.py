from __future__ import annotations

from dw_agent.metadata.datahub_mcp_provider import DataHubMcpProvider
from dw_agent.tools.datahub_mcp_client import DataHubMcpClient

DATASET_URN = "urn:li:dataset:(urn:li:dataPlatform:hive,dws_trade_channel_day_summary_di,PROD)"


def _mock_client() -> DataHubMcpClient:
    return DataHubMcpClient(
        enabled=False,
        mock_responses={
            "search": {
                "passed": True,
                "entities": [
                    {
                        "urn": DATASET_URN,
                        "name": "dws_trade_channel_day_summary_di",
                        "platform": "hive",
                        "description": "Certified channel daily summary for trade operations.",
                        "tags": [{"name": "Certified"}],
                        "score": 0.85,
                    }
                ],
            },
            "list_schema_fields": {
                "passed": True,
                "fields": [
                    {"fieldPath": "stat_date", "nativeDataType": "string", "description": "Report date"},
                    {"fieldPath": "channel_id", "nativeDataType": "string"},
                    {"fieldPath": "channel_name", "nativeDataType": "string"},
                    {"fieldPath": "channel_type", "nativeDataType": "string"},
                    {"fieldPath": "pay_amount", "nativeDataType": "decimal(18,2)"},
                    {"fieldPath": "refund_amount", "nativeDataType": "decimal(18,2)"},
                    {"fieldPath": "dt", "nativeDataType": "string"},
                ],
            },
            "get_entities": {
                "passed": True,
                "entities": [
                    {
                        "urn": DATASET_URN,
                        "owners": [{"name": "trade-data-owner", "type": "DATAOWNER"}],
                        "tags": [{"name": "Certified"}],
                        "glossaryTerms": [{"name": "Trade Metric"}],
                        "domain": "Commerce",
                        "dataProduct": "Channel Operations",
                    }
                ],
            },
            "get_lineage": {
                "passed": True,
                "entities": [
                    {
                        "urn": "urn:li:dataset:(urn:li:dataPlatform:hive,dwd_sales_detail_di,PROD)",
                        "name": "dwd_sales_detail_di",
                    }
                ],
            },
        },
    )


def test_datahub_provider_is_safe_when_disabled():
    provider = DataHubMcpProvider(client=DataHubMcpClient(enabled=False))

    assert provider.list_tables() == []
    assert provider.get_table("dws_trade_channel_day_summary_di") is None
    assert provider.search_tables(keyword="channel") == []


def test_datahub_provider_maps_assets_to_internal_metadata():
    provider = DataHubMcpProvider(client=_mock_client())

    table = provider.get_table("dws_trade_channel_day_summary_di")

    assert table is not None
    assert table["name"] == "dws_trade_channel_day_summary_di"
    assert table["layer"] == "DWS"
    assert table["table_type"] == "summary_fact"
    assert table["source"] == "datahub_mcp"
    assert table["owner"] == "trade-data-owner"
    assert table["certified"] is True
    assert table["partition_key"] == "dt"
    assert "pay_amount" in {field["name"] for field in table["fields"]}


def test_datahub_provider_search_summaries_scores_reusable_tables():
    provider = DataHubMcpProvider(client=_mock_client())

    tables = provider.search_summaries(
        dimensions=["channel"],
        metrics=["pay_amount", "refund_amount"],
        grain="stat_date + channel_id",
    )

    assert tables
    assert tables[0]["name"] == "dws_trade_channel_day_summary_di"
    assert tables[0]["score"] > 0
    assert tables[0]["missing_fields"] == []


def test_datahub_provider_exposes_lineage():
    provider = DataHubMcpProvider(client=_mock_client())

    lineage = provider.get_lineage(DATASET_URN)

    assert lineage
    assert lineage[0]["name"] == "dwd_sales_detail_di"
