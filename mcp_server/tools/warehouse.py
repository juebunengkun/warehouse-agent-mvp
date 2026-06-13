from __future__ import annotations

import json
from typing import Any

from dw_agent.config import DEFAULT_KB_PATH
from dw_agent.metadata import LocalJsonMetadataProvider
from dw_agent.nodes.common import METRIC_COLUMNS, METRIC_SQL
from dw_agent.tools import knowledge_search_tool, sql_validation_tool


def kb_path() -> str:
    return str(DEFAULT_KB_PATH)


def search_warehouse_docs(query: str, top_k: int = 4) -> list[dict[str, Any]]:
    results, _ = knowledge_search_tool(kb_path(), query, top_k=top_k)
    return results


def get_metric_definition(metric_name: str) -> dict[str, Any]:
    field, sql_type, comment = METRIC_COLUMNS.get(metric_name, ("", "", "未命中模拟指标库"))
    return {
        "metric": metric_name,
        "matched": metric_name in METRIC_COLUMNS,
        "field": field,
        "type": sql_type,
        "comment": comment,
        "expression": METRIC_SQL.get(metric_name, ""),
    }


def list_tables(layer: str | None = None) -> list[dict[str, Any]]:
    provider = _metadata_provider()
    requested_layer = layer.upper() if layer else None
    tables = []
    for table in provider.list_tables():
        table_layer = str(table.get("layer", "")).upper()
        if requested_layer and table_layer != requested_layer:
            continue
        tables.append(
            {
                "name": table.get("name"),
                "layer": table.get("layer"),
                "description": table.get("description"),
                "field_count": len(table.get("fields", [])),
            }
        )
    return tables


def get_table_schema(table_name: str) -> dict[str, Any]:
    table = _metadata_provider().get_table(table_name)
    if table:
        return {"matched": True, **table}
    return {"matched": False, "name": table_name, "fields": []}


def validate_sql(ddl: str, etl_sql: str, parsed_requirement: dict[str, Any] | str) -> dict[str, Any]:
    parsed = _coerce_parsed(parsed_requirement)
    validation, _ = sql_validation_tool(ddl, etl_sql, parsed)
    return validation


def health_check() -> dict[str, Any]:
    return {
        "status": "ok",
        "knowledge_base_path": kb_path(),
        "table_count": len(_metadata_provider().list_tables()),
        "metric_count": len(METRIC_COLUMNS),
    }


def _metadata_provider() -> LocalJsonMetadataProvider:
    return LocalJsonMetadataProvider(DEFAULT_KB_PATH)


def _coerce_parsed(parsed_requirement: dict[str, Any] | str) -> dict[str, Any]:
    if isinstance(parsed_requirement, dict):
        return parsed_requirement
    return json.loads(parsed_requirement)
