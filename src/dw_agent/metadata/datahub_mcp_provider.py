from __future__ import annotations

from typing import Any

from dw_agent.metadata.provider import (
    clone_table,
    field_names,
    metric_fields,
    metric_source_fields,
    normalize_grain,
    table_matches_business_process,
)
from dw_agent.metadata.selector import (
    choose_best_tables,
    score_dimension_table,
    score_fact_table,
    score_summary_table,
)
from dw_agent.metadata.semantic_mapper import enrich_table_metadata
from dw_agent.tools.datahub_mcp_client import DataHubMcpClient
from dw_agent.tools.datahub_mcp_tool import (
    get_datahub_dataset_schema,
    get_datahub_lineage,
    get_datahub_ownership,
    get_datahub_tags_and_terms,
    search_datahub_assets,
)


class DataHubMcpProvider:
    def __init__(self, config: dict[str, Any] | None = None, client: DataHubMcpClient | None = None) -> None:
        self.config = config or {}
        self.client = client or self.config.get("client") or DataHubMcpClient.from_env()

    def list_tables(self, keyword: str | None = None) -> list[dict[str, Any]]:
        if not self.client.is_enabled() and not self.client.mock_responses:
            return []
        query = keyword or self.config.get("default_query") or "warehouse dataset"
        return self.search_tables(keyword=str(query), top_k=int(self.config.get("default_limit", 10)))

    def get_table(self, table_name_or_urn: str) -> dict[str, Any] | None:
        if not self.client.is_enabled() and not self.client.mock_responses:
            return None
        urn = table_name_or_urn if table_name_or_urn.startswith("urn:") else None
        asset = None
        if urn is None:
            search = search_datahub_assets(table_name_or_urn, limit=1, client=self.client)
            assets = search.get("assets", []) if search.get("passed") else []
            if not assets:
                return None
            asset = assets[0]
            urn = str(asset.get("urn") or "")
        schema = get_datahub_dataset_schema(urn, client=self.client)
        ownership = get_datahub_ownership(urn, client=self.client)
        tags_terms = get_datahub_tags_and_terms(urn, client=self.client)
        return self._asset_to_table(asset or {"urn": urn, "name": _name_from_urn(urn)}, schema, ownership, tags_terms)

    def search_tables(
        self,
        *,
        keyword: str | None = None,
        layer: str | None = None,
        table_type: str | None = None,
        business_process: str | None = None,
        fields: set[str] | list[str] | None = None,
        metrics: list[str] | None = None,
        grain: set[str] | list[str] | str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        if not self.client.is_enabled() and not self.client.mock_responses:
            return []
        query = keyword or _query_from_filters(business_process, fields, metrics, grain)
        search = search_datahub_assets(query, limit=max(top_k, 10), client=self.client)
        if not search.get("passed"):
            return []

        requested_fields = set(fields or set()) | metric_fields(metrics or []) | metric_source_fields(metrics or [])
        requested_grain = normalize_grain(grain)
        scored = []
        for asset in search.get("assets", []):
            urn = str(asset.get("urn") or "")
            schema = get_datahub_dataset_schema(urn, client=self.client) if urn else {}
            ownership = get_datahub_ownership(urn, client=self.client) if urn else {}
            tags_terms = get_datahub_tags_and_terms(urn, client=self.client) if urn else {}
            table = self._asset_to_table(asset, schema, ownership, tags_terms)
            if layer and str(table.get("layer", "")).upper() != layer.upper():
                continue
            if table_type and table.get("table_type") != table_type:
                continue
            if business_process and not table_matches_business_process(table, business_process):
                continue
            scored.append(_score_table(table, requested_fields, requested_grain))
        return choose_best_tables(scored, top_k=top_k)

    def search_dimensions(self, semantic_dimensions: list[str]) -> list[dict[str, Any]]:
        selected: dict[str, dict[str, Any]] = {}
        query = " ".join(semantic_dimensions) or "dimension dataset"
        for table in self.search_tables(keyword=query, top_k=20):
            for dimension in semantic_dimensions:
                result = score_dimension_table(table, dimension)
                if result["score"] <= 0 or not result["covered_fields"]:
                    continue
                selected[str(table["name"])] = {**table, **result}
        return list(selected.values())

    def search_facts(self, metrics: list[str], business_process: str | None = None) -> list[dict[str, Any]]:
        scored = []
        for table in self.search_tables(keyword=" ".join([business_process or "", *metrics]), top_k=20):
            if str(table.get("layer", "")).upper() != "DWD":
                continue
            if table.get("table_type") not in {"transaction_fact", "snapshot_fact", "event_fact", "detail_fact"}:
                continue
            result = score_fact_table(table, metrics, business_process)
            if result["score"] <= 0 or not result["covered_fields"]:
                continue
            scored.append({**table, **result})
        return choose_best_tables(scored, top_k=3)

    def search_summaries(
        self,
        dimensions: list[str],
        metrics: list[str],
        grain: set[str] | list[str] | str | None = None,
        business_process: str | None = None,
    ) -> list[dict[str, Any]]:
        scored = []
        query = " ".join([business_process or "", *dimensions, *metrics])
        for table in self.search_tables(keyword=query, top_k=20):
            if str(table.get("layer", "")).upper() not in {"DWS", "ADS"}:
                continue
            if table.get("table_type") not in {"summary_fact", "application_report"}:
                continue
            result = score_summary_table(table, dimensions, metrics, grain, business_process)
            if result["score"] <= 0:
                continue
            scored.append({**table, **result})
        return choose_best_tables(scored, top_k=3)

    def get_lineage(self, table_name_or_urn: str, direction: str = "upstream") -> list[dict[str, Any]]:
        table = self.get_table(table_name_or_urn)
        urn = table.get("urn") if table else table_name_or_urn
        if not urn:
            return []
        result = get_datahub_lineage(str(urn), direction=direction, client=self.client)
        if not result.get("passed"):
            return []
        return list(result.get("lineage", []))

    def _asset_to_table(
        self,
        asset: dict[str, Any],
        schema: dict[str, Any] | None = None,
        ownership: dict[str, Any] | None = None,
        tags_terms: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        fields = [_field_to_internal(field) for field in (schema or {}).get("fields", [])]
        name = str(asset.get("name") or _name_from_urn(str(asset.get("urn") or "")))
        table = enrich_table_metadata(
            name=name,
            database=str(asset.get("platform") or "datahub"),
            schema=None,
            fields=fields,
            description=asset.get("description") or None,
        )
        owners = (ownership or {}).get("owners", [])
        tags = list(asset.get("tags", [])) or list((tags_terms or {}).get("tags", []))
        glossary_terms = list(asset.get("glossary_terms", [])) or list((tags_terms or {}).get("glossary_terms", []))
        table.update(
            {
                "urn": asset.get("urn"),
                "platform": asset.get("platform", "unknown"),
                "source": "datahub_mcp",
                "owner": _owner_name(owners) or asset.get("owner") or None,
                "tags": tags,
                "glossary_terms": glossary_terms,
                "domain": (tags_terms or {}).get("domain"),
                "data_product": (tags_terms or {}).get("data_product"),
                "certified": _is_certified(tags, glossary_terms),
                "confidence": asset.get("confidence", 0),
                "description": asset.get("description") or table.get("description"),
            }
        )
        return clone_table(table)


def _field_to_internal(field: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": field.get("name"),
        "type": field.get("type", "unknown"),
        "comment": field.get("description") or "",
        "nullable": field.get("nullable", True),
        "tags": field.get("tags", []),
        "glossary_terms": field.get("glossary_terms", []),
    }


def _score_table(table: dict[str, Any], requested_fields: set[str], requested_grain: set[str]) -> dict[str, Any]:
    available_fields = field_names(table)
    table_grain = normalize_grain(table.get("grain", ""))
    covered = requested_fields & available_fields
    score = int(table.get("confidence", 0) or 0)
    if requested_fields:
        score += int(60 * len(covered) / len(requested_fields))
    if requested_grain and requested_grain == table_grain:
        score += 18
    elif requested_grain and requested_grain.issubset(table_grain):
        score += 10
    if table.get("certified"):
        score += 8
    if table.get("partition_key"):
        score += 6
    if table.get("owner"):
        score += 3
    if not requested_fields:
        score += 1
    return {
        **table,
        "score": score,
        "covered_fields": sorted(covered),
        "missing_fields": sorted(requested_fields - available_fields),
    }


def _query_from_filters(
    business_process: str | None,
    fields: set[str] | list[str] | None,
    metrics: list[str] | None,
    grain: set[str] | list[str] | str | None,
) -> str:
    parts = [business_process or "", *(metrics or [])]
    parts.extend(str(field) for field in fields or [])
    parts.extend(sorted(normalize_grain(grain)))
    return " ".join(part for part in parts if part).strip() or "warehouse dataset"


def _is_certified(tags: list[str], glossary_terms: list[str]) -> bool:
    text = " ".join([*tags, *glossary_terms]).lower()
    return any(token in text for token in ["certified", "trusted", "gold"])


def _owner_name(owners: list[dict[str, Any]]) -> str | None:
    if not owners:
        return None
    return owners[0].get("name") or owners[0].get("email")


def _name_from_urn(urn: str) -> str:
    if not urn:
        return ""
    if urn.startswith("urn:li:dataset:(") and "(" in urn:
        parts = urn.split("(", 1)[1].rstrip(")").split(",")
        if len(parts) >= 2:
            return parts[1].split(".")[-1]
    return urn.rstrip(")").split(",")[-1].split(".")[-1]
