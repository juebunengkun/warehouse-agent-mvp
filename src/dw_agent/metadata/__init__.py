from __future__ import annotations

from pathlib import Path
from typing import Any

from dw_agent.metadata.local_json_provider import LocalJsonMetadataProvider
from dw_agent.metadata.mcp_provider import McpMetadataProvider
from dw_agent.metadata.provider import (
    MetadataProvider,
    field_names,
    get_metadata_provider,
    grain_fields,
    metric_fields,
    metric_source_fields,
    semantic_dimension_fields,
    table_suffix,
)


def load_table_metadata(kb_path: str | Path | None = None) -> list[dict[str, Any]]:
    return LocalJsonMetadataProvider(kb_path).list_tables()


def get_table_metadata(table_name: str, kb_path: str | Path | None = None) -> dict[str, Any] | None:
    return LocalJsonMetadataProvider(kb_path).get_table(table_name)


def find_tables_by_names(table_names: list[str], kb_path: str | Path | None = None) -> list[dict[str, Any]]:
    provider = LocalJsonMetadataProvider(kb_path)
    tables = []
    for table_name in table_names:
        table = provider.get_table(table_name)
        if table:
            tables.append(table)
    return tables


__all__ = [
    "MetadataProvider",
    "LocalJsonMetadataProvider",
    "McpMetadataProvider",
    "field_names",
    "find_tables_by_names",
    "get_metadata_provider",
    "get_table_metadata",
    "grain_fields",
    "load_table_metadata",
    "metric_fields",
    "metric_source_fields",
    "semantic_dimension_fields",
    "table_suffix",
]
