from __future__ import annotations


def test_metadata_provider_local_json():
    from dw_agent.metadata import LocalJsonMetadataProvider

    provider = LocalJsonMetadataProvider("knowledge_base")

    tables = provider.list_tables()
    dim_tables = provider.search_tables(layer="DIM")
    sales_summary = provider.get_table("dws_sales_day_summary_di")

    assert tables
    assert any(table["layer"] == "DIM" for table in dim_tables)
    assert sales_summary is not None
    assert sales_summary["fields"]
    assert sales_summary["grain"]
    assert sales_summary["primary_keys"]
    assert sales_summary["update_mode"] == "incremental"


def test_provider_selects_dimension_by_metadata_fields():
    from dw_agent.metadata import LocalJsonMetadataProvider
    from dw_agent.nodes.common import DIMENSION_COLUMNS

    channel_dimension = _dimension_for_field(DIMENSION_COLUMNS, "channel_id")
    provider = LocalJsonMetadataProvider("knowledge_base")

    matches = provider.search_dimensions([channel_dimension])

    assert matches
    assert matches[0]["table_type"] == "dimension"
    assert any(field["name"] == "channel_id" for field in matches[0]["fields"])


def _dimension_for_field(dimensions: dict, field_name: str) -> str:
    for dimension, fields in dimensions.items():
        if any(field[0] == field_name for field in fields):
            return dimension
    raise AssertionError(f"missing dimension for field {field_name}")
