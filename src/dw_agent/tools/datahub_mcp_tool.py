from __future__ import annotations

from typing import Any

from dw_agent.tools.datahub_mcp_client import DataHubMcpClient


def search_datahub_assets(
    query: str,
    entity_types: list[str] | None = None,
    limit: int = 10,
    *,
    client: DataHubMcpClient | None = None,
) -> dict[str, Any]:
    client = client or DataHubMcpClient.from_env()
    if not client.is_enabled() and not client.mock_responses:
        return _skipped("search_datahub_assets", "DataHub MCP is disabled.")
    raw = _call_first_available(
        client,
        ["search", "search_datahub_assets", "search_assets", "datahub_search"],
        {"query": query, "entity_types": entity_types or ["dataset"], "limit": limit, "count": limit},
    )
    if not raw.get("passed", True):
        return _tool_error("search_datahub_assets", raw)
    assets = [_normalize_asset(item) for item in _items(raw, "assets", "results", "entities")]
    return {
        "tool": "search_datahub_assets",
        "passed": True,
        "query": query,
        "assets": assets[:limit],
        "warnings": raw.get("warnings", []),
        "errors": [],
    }


def get_datahub_dataset_schema(
    dataset_urn: str,
    *,
    client: DataHubMcpClient | None = None,
) -> dict[str, Any]:
    client = client or DataHubMcpClient.from_env()
    if not client.is_enabled() and not client.mock_responses:
        return _skipped("get_datahub_dataset_schema", "DataHub MCP is disabled.")
    raw = _call_first_available(
        client,
        ["list_schema_fields", "get_datahub_dataset_schema", "get_dataset_schema", "datahub_get_schema", "get_schema"],
        {"dataset_urn": dataset_urn, "urn": dataset_urn, "count": 1000},
    )
    if not raw.get("passed", True):
        return _tool_error("get_datahub_dataset_schema", raw, dataset_urn=dataset_urn)
    fields = [_normalize_field(item) for item in _items(raw, "fields", "schema", "fieldSchemas")]
    return {
        "tool": "get_datahub_dataset_schema",
        "passed": True,
        "dataset_urn": dataset_urn,
        "fields": fields,
        "warnings": raw.get("warnings", []),
        "errors": [],
    }


def get_datahub_lineage(
    dataset_urn: str,
    direction: str = "upstream",
    depth: int = 1,
    *,
    client: DataHubMcpClient | None = None,
) -> dict[str, Any]:
    client = client or DataHubMcpClient.from_env()
    if not client.is_enabled() and not client.mock_responses:
        return _skipped("get_datahub_lineage", "DataHub MCP is disabled.")
    raw = _call_first_available(
        client,
        ["get_lineage", "get_datahub_lineage", "datahub_get_lineage"],
        {"dataset_urn": dataset_urn, "urn": dataset_urn, "direction": direction, "depth": depth},
    )
    if not raw.get("passed", True):
        return _tool_error("get_datahub_lineage", raw, dataset_urn=dataset_urn)
    lineage = [_normalize_lineage(item, direction) for item in _items(raw, "lineage", "entities", "results")]
    return {
        "tool": "get_datahub_lineage",
        "passed": True,
        "dataset_urn": dataset_urn,
        "direction": direction,
        "lineage": lineage,
        "warnings": raw.get("warnings", []),
        "errors": [],
    }


def get_datahub_ownership(
    dataset_urn: str,
    *,
    client: DataHubMcpClient | None = None,
) -> dict[str, Any]:
    client = client or DataHubMcpClient.from_env()
    if not client.is_enabled() and not client.mock_responses:
        return _skipped("get_datahub_ownership", "DataHub MCP is disabled.")
    raw = _call_first_available(
        client,
        ["get_entities", "get_datahub_ownership", "get_ownership", "datahub_get_ownership"],
        {"dataset_urn": dataset_urn, "urn": dataset_urn, "urns": [dataset_urn]},
    )
    if not raw.get("passed", True):
        return _tool_error("get_datahub_ownership", raw, dataset_urn=dataset_urn)
    entity = _first_entity(raw)
    owners = raw.get("owners") or raw.get("ownership") or entity.get("owners") or entity.get("ownership") or []
    return {
        "tool": "get_datahub_ownership",
        "passed": True,
        "dataset_urn": dataset_urn,
        "owners": [_normalize_owner(item) for item in _as_dict_list(owners)],
        "warnings": raw.get("warnings", []),
        "errors": [],
    }


def get_datahub_tags_and_terms(
    dataset_urn: str,
    *,
    client: DataHubMcpClient | None = None,
) -> dict[str, Any]:
    client = client or DataHubMcpClient.from_env()
    if not client.is_enabled() and not client.mock_responses:
        return _skipped("get_datahub_tags_and_terms", "DataHub MCP is disabled.")
    raw = _call_first_available(
        client,
        ["get_entities", "get_datahub_tags_and_terms", "get_tags_and_terms", "datahub_get_tags"],
        {"dataset_urn": dataset_urn, "urn": dataset_urn, "urns": [dataset_urn]},
    )
    if not raw.get("passed", True):
        return _tool_error("get_datahub_tags_and_terms", raw, dataset_urn=dataset_urn)
    entity = _first_entity(raw)
    tags = raw.get("tags", entity.get("tags", []))
    glossary_terms = raw.get(
        "glossary_terms", raw.get("glossaryTerms", entity.get("glossary_terms", entity.get("glossaryTerms", [])))
    )
    return {
        "tool": "get_datahub_tags_and_terms",
        "passed": True,
        "dataset_urn": dataset_urn,
        "tags": _string_list(tags),
        "glossary_terms": _string_list(glossary_terms),
        "domain": raw.get("domain") or entity.get("domain"),
        "data_product": raw.get("data_product")
        or raw.get("dataProduct")
        or entity.get("data_product")
        or entity.get("dataProduct"),
        "warnings": raw.get("warnings", []),
        "errors": [],
    }


def _call_first_available(client: DataHubMcpClient, tool_names: list[str], arguments: dict[str, Any]) -> dict[str, Any]:
    last_error: dict[str, Any] | None = None
    for tool_name in tool_names:
        result = client.call_tool(tool_name, arguments)
        if result.get("passed", True) or tool_name in client.mock_responses:
            return result
        last_error = result
    return last_error or {"passed": False, "errors": ["No DataHub MCP tool mapping is available."], "warnings": []}


def _items(raw: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = value.get("fields") or value.get("results") or value.get("items") or value.get("entities")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
    return []


def _normalize_asset(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "urn": item.get("urn") or item.get("id") or "",
        "name": item.get("name") or item.get("displayName") or _name_from_urn(item.get("urn", "")),
        "platform": item.get("platform") or item.get("platformName") or "unknown",
        "type": item.get("type") or item.get("entityType") or "dataset",
        "description": item.get("description") or "",
        "owner": _owner_name(item.get("owner") or item.get("owners")),
        "tags": _string_list(item.get("tags", [])),
        "glossary_terms": _string_list(item.get("glossary_terms", item.get("glossaryTerms", []))),
        "domain": item.get("domain"),
        "data_product": item.get("data_product") or item.get("dataProduct"),
        "confidence": float(item.get("confidence", item.get("score", 0.0)) or 0.0),
    }


def _normalize_field(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item.get("name") or item.get("fieldPath") or "",
        "type": item.get("type") or item.get("nativeDataType") or item.get("dataType") or "unknown",
        "description": item.get("description") or item.get("comment") or "",
        "nullable": bool(item.get("nullable", True)),
        "tags": _string_list(item.get("tags", [])),
        "glossary_terms": _string_list(item.get("glossary_terms", item.get("glossaryTerms", []))),
    }


def _normalize_lineage(item: dict[str, Any], direction: str) -> dict[str, Any]:
    return {
        "urn": item.get("urn") or item.get("id") or "",
        "name": item.get("name") or _name_from_urn(item.get("urn", "")),
        "type": item.get("type") or item.get("entityType") or "dataset",
        "relationship": item.get("relationship") or direction,
    }


def _normalize_owner(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": item.get("name") or item.get("owner") or item.get("urn") or "",
        "type": item.get("type") or item.get("ownershipType") or "DATAOWNER",
        "email": item.get("email") or "",
    }


def _tool_error(tool: str, raw: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {
        "tool": tool,
        "passed": False,
        "warnings": raw.get("warnings", []),
        "errors": raw.get("errors", []),
        **extra,
    }


def _skipped(tool: str, reason: str) -> dict[str, Any]:
    return {"tool": tool, "passed": False, "warnings": [reason], "errors": [], "skipped": True}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            result.append(str(item.get("name") or item.get("urn") or item.get("tag") or item.get("term") or ""))
    return [item for item in result if item]


def _first_entity(raw: dict[str, Any]) -> dict[str, Any]:
    entities = _items(raw, "entities", "results")
    return entities[0] if entities else {}


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        nested = value.get("owners") or value.get("items") or value.get("ownership")
        if isinstance(nested, list):
            return _as_dict_list(nested)
        return [value]
    if not isinstance(value, list):
        return []
    result = []
    for item in value:
        if isinstance(item, dict):
            result.append(item)
        elif isinstance(item, str):
            result.append({"name": item})
    return result


def _owner_name(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return _owner_name(value[0])
    if isinstance(value, dict):
        return str(value.get("name") or value.get("owner") or value.get("urn") or "")
    return ""


def _name_from_urn(urn: str) -> str:
    if not urn:
        return ""
    if urn.startswith("urn:li:dataset:(") and "(" in urn:
        parts = urn.split("(", 1)[1].rstrip(")").split(",")
        if len(parts) >= 2:
            return parts[1].split(".")[-1]
    return urn.rstrip(")").split(",")[-1].split(".")[-1]
