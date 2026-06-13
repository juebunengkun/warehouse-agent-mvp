from __future__ import annotations

from typing import Any

from dw_agent.metadata.provider import (
    field_names,
    grain_fields,
    metric_fields,
    metric_source_fields,
    normalize_grain,
    semantic_dimension_fields,
    table_matches_business_process,
)


def score_dimension_table(table: dict[str, Any], semantic_dimension: str) -> dict[str, Any]:
    required_fields = semantic_dimension_fields([semantic_dimension])
    available_fields = field_names(table)
    covered = required_fields & available_fields
    score = 0

    if str(table.get("layer", "")).upper() == "DIM":
        score += 30
    if table.get("table_type") == "dimension":
        score += 25
    if required_fields:
        score += int(30 * len(covered) / len(required_fields))
    if grain_fields(table) & required_fields:
        score += 8
    score += _metadata_quality_score(table)

    return {
        "score": score,
        "required_fields": sorted(required_fields),
        "covered_fields": sorted(covered),
        "missing_fields": sorted(required_fields - available_fields),
    }


def score_fact_table(table: dict[str, Any], metrics: list[str], business_process: str | None = None) -> dict[str, Any]:
    required_fields = metric_source_fields(metrics)
    metric_aliases = metric_fields(metrics)
    available_fields = field_names(table)
    covered = required_fields & available_fields
    covered_metrics = metric_aliases & available_fields
    score = 0

    if str(table.get("layer", "")).upper() == "DWD":
        score += 25
    if table.get("table_type") in {"transaction_fact", "event_fact", "detail_fact"}:
        score += 25
    if required_fields:
        score += int(35 * len(covered) / len(required_fields))
    if covered_metrics:
        score += int(10 * len(covered_metrics) / max(len(metric_aliases), 1))
    if table_matches_business_process(table, business_process):
        score += 12
    score += _metadata_quality_score(table)

    return {
        "score": score,
        "required_fields": sorted(required_fields),
        "covered_fields": sorted(covered | covered_metrics),
        "missing_fields": sorted(required_fields - available_fields),
    }


def score_summary_table(
    table: dict[str, Any],
    dimensions: list[str],
    metrics: list[str],
    grain: set[str] | list[str] | str | None = None,
    business_process: str | None = None,
) -> dict[str, Any]:
    required_dim_fields = semantic_dimension_fields(dimensions)
    required_metric_fields = metric_fields(metrics)
    required_fields = required_dim_fields | required_metric_fields
    requested_grain = normalize_grain(grain) or required_dim_fields
    available_fields = field_names(table)
    table_grain = grain_fields(table)
    covered = required_fields & available_fields
    missing = required_fields - available_fields
    score = 0

    layer = str(table.get("layer", "")).upper()
    if layer == "DWS":
        score += 30
    elif layer == "ADS":
        score += 12
    if table.get("table_type") in {"summary_fact", "application_report"}:
        score += 20
    if required_fields:
        score += int(35 * len(covered) / len(required_fields))
    if requested_grain and requested_grain == table_grain:
        score += 18
    elif requested_grain and requested_grain.issubset(table_grain):
        score += 10
    if table_matches_business_process(table, business_process):
        score += 12
    score += _metadata_quality_score(table)

    return {
        "score": score,
        "required_fields": sorted(required_fields),
        "covered_fields": sorted(covered),
        "missing_fields": sorted(missing),
        "requested_grain": sorted(requested_grain),
        "table_grain": sorted(table_grain),
    }


def choose_best_tables(candidates: list[dict[str, Any]], top_k: int = 3) -> list[dict[str, Any]]:
    return sorted(candidates, key=lambda item: item.get("score", 0), reverse=True)[:top_k]


def _metadata_quality_score(table: dict[str, Any]) -> int:
    score = 0
    if table.get("primary_keys"):
        score += 4
    if table.get("foreign_keys"):
        score += 3
    if table.get("partition_key"):
        score += 5
    if table.get("update_mode") in {"incremental", "full_snapshot", "snapshot"}:
        score += 4
    if table.get("certified"):
        score += 6
    if table.get("sla_time"):
        score += 3
    return score
