from __future__ import annotations

from typing import Any

KEY_FIELD_CANDIDATES = {
    "order_id",
    "user_id",
    "sku_id",
    "item_id",
    "channel_id",
    "region_id",
    "category_id",
    "event_id",
}

SUMMARY_DIMENSION_FIELDS = {
    "stat_date",
    "channel_id",
    "channel_name",
    "channel_type",
    "region_id",
    "province_name",
    "city_name",
    "user_id",
    "user_type",
    "member_level",
    "category_id",
    "category_level1_name",
    "category_level2_name",
    "sku_id",
    "sku_name",
}

FACT_TOKENS = {
    "order",
    "pay",
    "refund",
    "event",
    "log",
    "click",
    "exposure",
    "visit",
    "cart",
    "gmv",
}


def enrich_table_metadata(
    *,
    name: str,
    fields: list[dict[str, Any]],
    database: str | None = None,
    schema: str | None = None,
    primary_keys: list[str] | None = None,
    foreign_keys: list[dict[str, Any]] | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    field_names = [str(field.get("name", "")) for field in fields if field.get("name")]
    text = _semantic_text(name, fields, description)
    layer = infer_layer(name)
    inferred_primary_keys = primary_keys or infer_primary_keys(field_names, layer)
    grain = infer_grain(field_names, layer, inferred_primary_keys)
    return {
        "name": name,
        "database": database,
        "schema": schema,
        "layer": layer,
        "business_process": infer_business_process(name, fields, description),
        "table_type": infer_table_type(name, field_names, layer, text),
        "grain": grain,
        "primary_keys": inferred_primary_keys,
        "foreign_keys": foreign_keys or infer_foreign_keys(name, field_names),
        "fields": fields,
        "update_mode": infer_update_mode(name),
        "partition_key": infer_partition_key(field_names),
        "owner": None,
        "sla_time": None,
        "certified": False,
        "description": description,
        "source": "information_schema",
        "risk_notes": [] if grain else ["grain inferred as unknown; manual review required"],
    }


def infer_layer(table_name: str) -> str:
    lowered = table_name.lower()
    for prefix, layer in [
        ("ods_", "ODS"),
        ("dwd_", "DWD"),
        ("dim_", "DIM"),
        ("dws_", "DWS"),
        ("ads_", "ADS"),
    ]:
        if lowered.startswith(prefix):
            return layer
    return "UNKNOWN"


def infer_update_mode(table_name: str) -> str:
    lowered = table_name.lower()
    if lowered.endswith("_di"):
        return "incremental"
    if lowered.endswith("_df"):
        return "full_snapshot"
    if lowered.endswith("_mi"):
        return "monthly_incremental"
    return "unknown"


def infer_table_type(table_name: str, field_names: list[str], layer: str, semantic_text: str | None = None) -> str:
    if layer == "DIM":
        return "dimension"
    if layer == "DWS":
        return "summary_fact"
    if layer == "ADS":
        return "application_report"
    if layer == "DWD":
        text = semantic_text or " ".join([table_name, *field_names]).lower()
        if any(token in text for token in FACT_TOKENS):
            return "transaction_fact"
        return "snapshot_fact"
    return "unknown"


def infer_partition_key(field_names: list[str]) -> str | None:
    lowered = {field.lower(): field for field in field_names}
    for candidate in ["dt", "ds", "stat_date"]:
        if candidate in lowered:
            return lowered[candidate]
    return None


def infer_primary_keys(field_names: list[str], layer: str) -> list[str]:
    available = {field.lower(): field for field in field_names}
    if layer in {"DWS", "ADS"}:
        dimensions = [field for field in field_names if field in SUMMARY_DIMENSION_FIELDS]
        return dimensions
    return [available[name] for name in KEY_FIELD_CANDIDATES if name in available]


def infer_grain(field_names: list[str], layer: str, primary_keys: list[str]) -> str | None:
    if primary_keys:
        return " + ".join(primary_keys)
    if layer in {"DWS", "ADS"}:
        dimensions = [field for field in field_names if field in SUMMARY_DIMENSION_FIELDS]
        if dimensions:
            return " + ".join(dimensions)
    return None


def infer_business_process(table_name: str, fields: list[dict[str, Any]], description: str | None = None) -> str:
    text = _semantic_text(table_name, fields, description)
    if "category" in text and ("channel" in text or "operation" in text or "summary" in text or "report" in text):
        return "category_operation"
    if any(token in text for token in ["order", "pay", "refund", "gmv"]):
        return "trade_order"
    if any(token in text for token in ["visit", "exposure", "click", "cart", "behavior"]):
        return "traffic_behavior"
    if any(token in text for token in ["user", "profile", "member"]):
        return "user_profile"
    if "channel" in text:
        return "channel"
    if any(token in text for token in ["region", "province", "city"]):
        return "region"
    if any(token in text for token in ["category", "sku", "item", "product"]):
        return "product_category"
    return "unknown"


def infer_foreign_keys(table_name: str, field_names: list[str]) -> list[dict[str, Any]]:
    if infer_layer(table_name) != "DWD":
        return []
    refs = {
        "channel_id": "dim_channel_df",
        "region_id": "dim_region_df",
        "user_id": "dim_user_profile_df",
        "category_id": "dim_category_df",
    }
    available = {field.lower() for field in field_names}
    foreign_keys = []
    for field, ref_table in refs.items():
        if field not in available:
            continue
        foreign_keys.append(
            {
                "field": field,
                "ref_table": ref_table,
                "ref_field": field,
                "join_type": "left_join",
                "partition_mapping": f"{ref_table}.dt='${{bizdate}}'",
            }
        )
    return foreign_keys


def _semantic_text(table_name: str, fields: list[dict[str, Any]], description: str | None = None) -> str:
    parts = [table_name, description or ""]
    for field in fields:
        parts.append(str(field.get("name") or ""))
        parts.append(str(field.get("comment") or ""))
    return " ".join(parts).lower()
