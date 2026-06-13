from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dw_agent.config import DEFAULT_KB_PATH
from dw_agent.metadata.provider import (
    clone_table,
    field_names,
    metric_fields,
    metric_source_fields,
    normalize_grain,
    semantic_dimension_fields,
    table_matches_business_process,
)
from dw_agent.metadata.selector import (
    choose_best_tables,
    score_dimension_table,
    score_fact_table,
    score_summary_table,
)


class LocalJsonMetadataProvider:
    def __init__(self, kb_path: str | Path | None = None) -> None:
        self.kb_path = Path(kb_path) if kb_path else DEFAULT_KB_PATH

    @property
    def metadata_path(self) -> Path:
        return self.kb_path / "table_metadata.json"

    def list_tables(self) -> list[dict[str, Any]]:
        data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        return [clone_table(table) for table in data.get("tables", [])]

    def get_table(self, table_name: str) -> dict[str, Any] | None:
        for table in self.list_tables():
            if table.get("name") == table_name:
                return table
        return None

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
    ) -> list[dict[str, Any]]:
        requested_fields = set(fields or set()) | metric_fields(metrics or []) | metric_source_fields(metrics or [])
        requested_grain = normalize_grain(grain)
        scored = []
        for table in self.list_tables():
            if layer and str(table.get("layer", "")).upper() != layer.upper():
                continue
            if table_type and table.get("table_type") != table_type:
                continue
            if business_process and not table_matches_business_process(table, business_process):
                continue

            available_fields = field_names(table)
            table_grain = normalize_grain(table.get("grain", ""))
            covered = requested_fields & available_fields
            score = 0
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
            if table.get("sla_time"):
                score += 3
            if not requested_fields:
                score += 1

            scored.append(
                {
                    **table,
                    "score": score,
                    "covered_fields": sorted(covered),
                    "missing_fields": sorted(requested_fields - available_fields),
                }
            )
        return choose_best_tables(scored, top_k=top_k)

    def search_dimensions(self, semantic_dimensions: list[str]) -> list[dict[str, Any]]:
        selected: dict[str, dict[str, Any]] = {}
        for dimension in semantic_dimensions:
            required_fields = semantic_dimension_fields([dimension])
            if required_fields == {"stat_date"}:
                continue
            scored = []
            for table in self.list_tables():
                result = score_dimension_table(table, dimension)
                if result["score"] <= 0 or not result["covered_fields"]:
                    continue
                scored.append({**table, **result})
            for table in choose_best_tables(scored, top_k=1):
                selected[str(table["name"])] = table
        return list(selected.values())

    def search_facts(self, metrics: list[str], business_process: str | None = None) -> list[dict[str, Any]]:
        scored = []
        for table in self.list_tables():
            if str(table.get("layer", "")).upper() != "DWD":
                continue
            if table.get("table_type") not in {"transaction_fact", "event_fact", "detail_fact"}:
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
        for table in self.list_tables():
            if str(table.get("layer", "")).upper() != "DWS":
                continue
            if table.get("table_type") != "summary_fact":
                continue
            result = score_summary_table(table, dimensions, metrics, grain, business_process)
            if result["score"] <= 0:
                continue
            scored.append({**table, **result})
        return choose_best_tables(scored, top_k=3)
