from __future__ import annotations

from typing import Any

from dw_agent.metadata.local_json_provider import LocalJsonMetadataProvider
from dw_agent.metadata.provider import MetadataProvider


class McpMetadataProvider:
    """Thin wrapper reserved for production MCP-backed metadata.

    The current MVP keeps LocalJson as the default provider. This class keeps
    the same interface so production code can swap in MCP/DataHub/Hive metadata
    without changing modeling nodes.
    """

    def __init__(self, config: dict[str, Any] | None = None, fallback: MetadataProvider | None = None) -> None:
        self.config = config or {}
        self.fallback = fallback or LocalJsonMetadataProvider(self.config.get("knowledge_base_path"))

    def list_tables(self) -> list[dict[str, Any]]:
        try:
            from dw_agent.mcp_client import call_mcp_tool

            tables = call_mcp_tool("list_tables_tool", {"layer": None})
            if isinstance(tables, list):
                detailed = []
                for table in tables:
                    name = table.get("name") if isinstance(table, dict) else None
                    if not name:
                        continue
                    schema = self.get_table(name)
                    if schema:
                        detailed.append(schema)
                return detailed
        except Exception:
            return self.fallback.list_tables()
        return self.fallback.list_tables()

    def get_table(self, table_name: str) -> dict[str, Any] | None:
        try:
            from dw_agent.mcp_client import call_mcp_tool

            schema = call_mcp_tool("get_table_schema_tool", {"table_name": table_name})
            if isinstance(schema, dict) and schema.get("matched"):
                return {key: value for key, value in schema.items() if key != "matched"}
        except Exception:
            return self.fallback.get_table(table_name)
        return self.fallback.get_table(table_name)

    def search_tables(self, **kwargs) -> list[dict[str, Any]]:
        return _as_local_provider(self.list_tables()).search_tables(**kwargs)

    def search_dimensions(self, semantic_dimensions: list[str]) -> list[dict[str, Any]]:
        return _as_local_provider(self.list_tables()).search_dimensions(semantic_dimensions)

    def search_facts(self, metrics: list[str], business_process: str | None = None) -> list[dict[str, Any]]:
        return _as_local_provider(self.list_tables()).search_facts(metrics, business_process)

    def search_summaries(
        self,
        dimensions: list[str],
        metrics: list[str],
        grain=None,
        business_process: str | None = None,
    ) -> list[dict[str, Any]]:
        return _as_local_provider(self.list_tables()).search_summaries(dimensions, metrics, grain, business_process)


def _as_local_provider(tables: list[dict[str, Any]]) -> LocalJsonMetadataProvider:
    provider = LocalJsonMetadataProvider()
    provider.list_tables = lambda: tables  # type: ignore[method-assign]
    provider.get_table = lambda table_name: next((table for table in tables if table.get("name") == table_name), None)  # type: ignore[method-assign]
    return provider
