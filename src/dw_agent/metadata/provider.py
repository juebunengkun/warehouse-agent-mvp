from __future__ import annotations

import os
import re
from typing import Any, Protocol

from dw_agent.config import DEFAULT_KB_PATH
from dw_agent.nodes.common import METRIC_COLUMNS, dimension_columns, metric_columns, metric_expression


class MetadataProvider(Protocol):
    def list_tables(self) -> list[dict[str, Any]]: ...

    def get_table(self, table_name: str) -> dict[str, Any] | None: ...

    def search_tables(
        self,
        *,
        layer: str | None = None,
        table_type: str | None = None,
        business_process: str | None = None,
        fields: set[str] | list[str] | None = None,
        metrics: list[str] | None = None,
        grain: set[str] | list[str] | str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]: ...

    def search_dimensions(self, semantic_dimensions: list[str]) -> list[dict[str, Any]]: ...

    def search_facts(self, metrics: list[str], business_process: str | None = None) -> list[dict[str, Any]]: ...

    def search_summaries(
        self,
        dimensions: list[str],
        metrics: list[str],
        grain: set[str] | list[str] | str | None = None,
        business_process: str | None = None,
    ) -> list[dict[str, Any]]: ...


def get_metadata_provider(config: dict[str, Any] | None = None) -> MetadataProvider:
    config = config or {}
    provider_type = str(
        config.get("type") or config.get("provider") or os.getenv("WAREHOUSE_METADATA_PROVIDER") or "local_json"
    ).lower()
    if provider_type in {"information_schema", "infoschema", "database"}:
        from dw_agent.metadata.information_schema_provider import InformationSchemaMetadataProvider

        return InformationSchemaMetadataProvider(config=config)
    if provider_type in {"mcp", "mcp_metadata"}:
        from dw_agent.metadata.mcp_provider import McpMetadataProvider

        return McpMetadataProvider(config=config)

    from dw_agent.metadata.local_json_provider import LocalJsonMetadataProvider

    kb_path = config.get("knowledge_base_path") or config.get("kb_path") or DEFAULT_KB_PATH
    return LocalJsonMetadataProvider(kb_path)


def table_suffix(table_name: str) -> str:
    if table_name.endswith("_di"):
        return "_di"
    if table_name.endswith("_df"):
        return "_df"
    return ""


def field_names(table: dict[str, Any]) -> set[str]:
    return {str(field.get("name")) for field in table.get("fields", []) if field.get("name")}


def grain_fields(table: dict[str, Any]) -> set[str]:
    return normalize_grain(table.get("grain", ""))


def normalize_grain(grain: set[str] | list[str] | str | None) -> set[str]:
    if grain is None:
        return set()
    if isinstance(grain, set):
        return {str(item).strip() for item in grain if str(item).strip()}
    if isinstance(grain, list):
        return {str(item).strip() for item in grain if str(item).strip()}
    return {item.strip() for item in re.split(r"[+/,，、\s-]+", str(grain)) if item.strip()}


def semantic_dimension_fields(dimensions: list[str]) -> set[str]:
    fields: set[str] = set()
    for _, field, _, _ in dimension_columns(dimensions):
        fields.add(field)

    semantic_aliases = {
        "类目": {"category_id", "category_level1_name", "category_level2_name"},
        "品类": {"category_id", "category_level1_name", "category_level2_name"},
        "category": {"category_id", "category_level1_name", "category_level2_name"},
        "channel": {"channel_id", "channel_name", "channel_type"},
        "region": {"region_id", "province_name", "city_name"},
        "user": {"user_id", "user_type", "member_level"},
    }
    for dimension in dimensions:
        dimension_text = str(dimension)
        lowered = dimension_text.lower()
        for keyword, aliases in semantic_aliases.items():
            if keyword in lowered or keyword in dimension_text:
                fields.update(aliases)
    return fields


def metric_fields(metrics: list[str]) -> set[str]:
    fields = {field for _, field, _, _ in metric_columns(metrics)}
    for metric in metrics:
        metric_text = str(metric).strip()
        if metric_text not in METRIC_COLUMNS and re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", metric_text):
            fields.add(metric_text)
    return fields


def metric_source_fields(metrics: list[str]) -> set[str]:
    fields = set(metric_fields(metrics))
    metric_aliases = {
        "访问": {"visit_user_id", "visit_user_cnt"},
        "曝光": {"event_type", "exposure_user_id", "exposure_cnt"},
        "点击": {"event_type", "click_user_id", "click_cnt"},
        "加购": {"event_type", "cart_user_id", "cart_user_cnt"},
        "下单": {"order_id", "order_user_id", "order_user_cnt"},
        "支付": {"pay_amount", "pay_user_cnt", "pay_order_cnt"},
        "退款": {"refund_amount", "refund_order_cnt"},
        "visit": {"visit_user_id", "visit_user_cnt"},
        "exposure": {"event_type", "exposure_user_id", "exposure_cnt"},
        "click": {"event_type", "click_user_id", "click_cnt"},
        "cart": {"event_type", "cart_user_id", "cart_user_cnt"},
        "pay": {"pay_amount", "pay_user_cnt", "pay_order_cnt"},
        "refund": {"refund_amount", "refund_order_cnt"},
    }
    for metric in metrics:
        metric_text = str(metric)
        lowered_metric = metric_text.lower()
        for keyword, aliases in metric_aliases.items():
            if keyword in lowered_metric or keyword in metric_text:
                fields.update(aliases)
        expression = metric_expression(metric)
        for token in re.findall(r"\b[a-zA-Z_][a-zA-Z0-9_]*\b", expression):
            upper = token.upper()
            if upper in {"SUM", "COUNT", "DISTINCT", "CASE", "WHEN", "THEN", "ELSE", "END", "NULLIF", "CAST", "AS"}:
                continue
            if upper in {"PAID", "FINISHED"}:
                continue
            fields.add(token)
    return fields


def clone_table(table: dict[str, Any]) -> dict[str, Any]:
    cloned = dict(table)
    cloned["fields"] = [dict(field) for field in table.get("fields", [])]
    cloned["primary_keys"] = list(table.get("primary_keys", []))
    cloned["foreign_keys"] = [dict(key) for key in table.get("foreign_keys", [])]
    return cloned


def table_matches_business_process(table: dict[str, Any], business_process: str | None) -> bool:
    if not business_process:
        return True
    table_process = str(table.get("business_process", ""))
    if table_process in {business_process, "general_report", "unknown"} or business_process in table_process:
        return True
    compatible = {
        "category_operation": {"product_category", "trade_order", "traffic_behavior", "channel_operation"},
        "channel_operation": {"traffic_behavior", "trade_order", "category_operation"},
        "trade_order": {"category_operation", "channel_operation"},
        "traffic_behavior": {"category_operation", "channel_operation"},
    }
    return table_process in compatible.get(business_process, set())


def safe_table_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip().lower())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "generated_table"
