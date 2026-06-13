from __future__ import annotations

from typing import Any

from dw_agent.metadata import (
    field_names,
    get_metadata_provider,
    metric_source_fields,
    semantic_dimension_fields,
    table_suffix,
)
from dw_agent.nodes.common import dimension_columns, group_fields, metric_columns, table_names
from dw_agent.nodes.decide_table_reuse import infer_business_process
from dw_agent.state import AgentState


def decide_modeling_strategy(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    kb_path = state.get("knowledge_base_path")
    provider = get_metadata_provider({"knowledge_base_path": kb_path})
    generated_names = table_names(parsed)
    business_process = infer_business_process(parsed)
    reuse_decision = state.get("reuse_decision", {})

    dimensions = parsed.get("dimensions", [])
    metrics = parsed.get("metrics", [])
    requested_grain = set(group_fields(parsed))
    report_fields = _report_fields(parsed)

    dim_tables = [_table_entry(table, _reason_for_table(table)) for table in provider.search_dimensions(dimensions)]
    fact_tables = [
        _table_entry(table, _reason_for_table(table)) for table in provider.search_facts(metrics, business_process)
    ]
    if not fact_tables:
        fact_tables = [
            _planned_entry(
                generated_names["dwd"],
                "DWD",
                "transaction_fact",
                "detail_event",
                fields=_fallback_fact_fields(parsed),
            )
        ]

    source_tables = provider.search_tables(
        layer="ODS",
        table_type="raw_event",
        business_process=business_process,
        fields=metric_source_fields(metrics) | semantic_dimension_fields(dimensions),
        top_k=2,
    )
    if not source_tables:
        source_tables = provider.search_tables(
            layer="ODS", table_type="raw_event", fields=metric_source_fields(metrics), top_k=1
        )
    source_tables = [_table_entry(table, _reason_for_table(table)) for table in source_tables]

    summary_tables = _summary_tables(
        provider=provider,
        parsed=parsed,
        reuse_decision=reuse_decision,
        generated_name=generated_names["dws"],
        report_fields=report_fields,
        business_process=business_process,
        requested_grain=requested_grain,
    )

    application_tables = _application_tables(
        provider=provider,
        parsed=parsed,
        generated_name=generated_names["ads"],
        report_fields=[*report_fields, {"name": "update_time", "type": "STRING", "comment": "data update time"}],
        business_process=business_process,
        requested_grain=requested_grain,
    )

    join_plan = _build_join_plan(fact_tables, dim_tables)
    dependency_plan = _build_dependency_plan(dim_tables, fact_tables, summary_tables, application_tables, source_tables)
    risk_notes = _risk_notes(reuse_decision, fact_tables, dim_tables, summary_tables)

    strategy = {
        "business_process": business_process,
        "source_tables": source_tables,
        "fact_tables": fact_tables,
        "dim_tables": dim_tables,
        "summary_tables": summary_tables,
        "application_tables": application_tables,
        "join_plan": join_plan,
        "dependency_plan": dependency_plan,
        "reuse_mode": reuse_decision.get("decision") == "reuse_existing_dws",
        "risk_notes": risk_notes,
    }

    trace = [
        *state.get("tool_trace", []),
        {
            "tool": "modeling_strategy",
            "input": {
                "business_process": business_process,
                "dimensions": dimensions,
                "metrics": metrics,
                "provider": provider.__class__.__name__,
            },
            "output": {
                "fact_tables": [table["name"] for table in fact_tables],
                "dim_tables": [table["name"] for table in dim_tables],
                "summary_tables": [table["name"] for table in summary_tables],
                "application_tables": [table["name"] for table in application_tables],
            },
        },
    ]
    return {**state, "modeling_strategy": strategy, "tool_trace": trace}


def _summary_tables(
    *,
    provider,
    parsed: dict[str, Any],
    reuse_decision: dict[str, Any],
    generated_name: str,
    report_fields: list[dict[str, Any]],
    business_process: str,
    requested_grain: set[str],
) -> list[dict[str, Any]]:
    if reuse_decision.get("decision") == "reuse_existing_dws" and reuse_decision.get("table"):
        table = provider.get_table(reuse_decision["table"])
        if table:
            return [
                {
                    **_table_entry(table, "provider selected reusable DWS that satisfies hard checks"),
                    "reuse": True,
                }
            ]

    candidates = provider.search_summaries(
        parsed.get("dimensions", []),
        parsed.get("metrics", []),
        requested_grain,
        business_process,
    )
    if candidates:
        candidate = candidates[0]
        return [
            {
                **_table_entry(candidate, "provider ranked existing DWS as nearest summary candidate"),
                "reuse": False,
            }
        ]

    return [
        {
            **_planned_entry(
                generated_name,
                "DWS",
                "summary_fact",
                " + ".join(sorted(requested_grain)) or parsed.get("granularity", "unknown"),
                fields=report_fields,
            ),
            "reuse": False,
        }
    ]


def _application_tables(
    *,
    provider,
    parsed: dict[str, Any],
    generated_name: str,
    report_fields: list[dict[str, Any]],
    business_process: str,
    requested_grain: set[str],
) -> list[dict[str, Any]]:
    fields = {field["name"] for field in report_fields if field.get("name")}
    candidates = provider.search_tables(
        layer="ADS",
        table_type="application_report",
        business_process=business_process,
        fields=fields,
        grain=requested_grain,
        top_k=1,
    )
    if candidates and not candidates[0].get("missing_fields"):
        return [_table_entry(candidates[0], "provider selected application report table by fields and grain")]
    return [
        _planned_entry(
            generated_name,
            "ADS",
            "application_report",
            " + ".join(sorted(requested_grain)) or parsed.get("granularity", "unknown"),
            fields=report_fields,
        )
    ]


def _table_entry(table: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "name": table.get("name"),
        "layer": table.get("layer"),
        "table_type": table.get("table_type", ""),
        "grain": table.get("grain", ""),
        "primary_keys": table.get("primary_keys", []),
        "foreign_keys": table.get("foreign_keys", []),
        "update_mode": table.get("update_mode", ""),
        "suffix": table_suffix(table.get("name", "")),
        "partition_key": table.get("partition_key", ""),
        "owner": table.get("owner", ""),
        "sla_time": table.get("sla_time", ""),
        "certified": table.get("certified", False),
        "description": table.get("description", ""),
        "fields": table.get("fields", []),
        "score": table.get("score"),
        "covered_fields": table.get("covered_fields", []),
        "missing_fields": table.get("missing_fields", []),
        "reason": reason,
    }


def _planned_entry(
    name: str,
    layer: str,
    table_type: str,
    grain: str,
    *,
    fields: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "layer": layer,
        "table_type": table_type,
        "grain": grain,
        "primary_keys": [],
        "foreign_keys": [],
        "update_mode": "incremental",
        "suffix": table_suffix(name),
        "partition_key": "dt",
        "owner": "report_data",
        "sla_time": "08:30",
        "certified": False,
        "description": "planned table generated from requirement metadata",
        "fields": fields or [],
        "reason": "no fully reusable provider table found; plan a new table at requested grain",
    }


def _reason_for_table(table: dict[str, Any]) -> str:
    layer = table.get("layer", "")
    table_type = table.get("table_type", "")
    score = table.get("score")
    suffix = f", score={score}" if score is not None else ""
    return f"selected from metadata provider by layer={layer}, table_type={table_type}{suffix}"


def _report_fields(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    columns = [*dimension_columns(parsed.get("dimensions", [])), *metric_columns(parsed.get("metrics", []))]
    fields: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, field_name, sql_type, comment in columns:
        if field_name in seen:
            continue
        seen.add(field_name)
        fields.append({"name": field_name, "type": sql_type, "comment": comment})
    fields.append({"name": "dt", "type": "STRING", "comment": "partition date"})
    return fields


def _fallback_fact_fields(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    fields = _report_fields(parsed)
    if not any(field["name"] == "event_id" for field in fields):
        fields.insert(0, {"name": "event_id", "type": "STRING", "comment": "source event id"})
    return fields


def _build_join_plan(fact_tables: list[dict[str, Any]], dim_tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    dim_by_name = {str(table.get("name")): table for table in dim_tables if table.get("name")}
    joins = []
    for fact in fact_tables:
        for foreign_key in fact.get("foreign_keys", []):
            right_table = _resolve_dim_table(foreign_key, dim_by_name)
            if not right_table:
                continue
            left_key = foreign_key.get("field", "")
            right_key = foreign_key.get("ref_field") or left_key
            if not left_key or not right_key:
                continue
            right_name = str(right_table.get("name"))
            partition_condition = _partition_condition(foreign_key, right_name)
            joins.append(
                {
                    "left_table": fact["name"],
                    "right_table": right_name,
                    "join_type": foreign_key.get("join_type", "left_join"),
                    "join_keys": [left_key],
                    "right_keys": [right_key],
                    "partition_condition": partition_condition,
                    "risk": f"verify {right_name}.{right_key} uniqueness before publishing",
                }
            )
    return joins


def _resolve_dim_table(foreign_key: dict[str, Any], dim_by_name: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    ref_table = foreign_key.get("ref_table")
    if ref_table in dim_by_name:
        return dim_by_name[ref_table]

    ref_field = foreign_key.get("ref_field") or foreign_key.get("field")
    if not ref_field:
        return None
    for table in dim_by_name.values():
        if ref_field in field_names(table):
            return table
    return None


def _partition_condition(foreign_key: dict[str, Any], right_table: str) -> str:
    condition = foreign_key.get("partition_mapping")
    ref_table = foreign_key.get("ref_table")
    if condition and ref_table and ref_table in condition:
        return condition.replace(ref_table, right_table)
    if condition and right_table in condition:
        return condition
    return f"{right_table}.dt='${{bizdate}}'"


def _build_dependency_plan(
    dim_tables: list[dict[str, Any]],
    fact_tables: list[dict[str, Any]],
    summary_tables: list[dict[str, Any]],
    application_tables: list[dict[str, Any]],
    source_tables: list[dict[str, Any]],
) -> list[str]:
    ordered_tables = [*source_tables, *dim_tables, *fact_tables, *summary_tables, *application_tables]
    dependencies = []
    seen: set[str] = set()
    for table in ordered_tables:
        name = table.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        dependencies.append(f"{name} {table.get('partition_key') or 'dt'}=${{bizdate}}")
    return dependencies


def _risk_notes(
    reuse_decision: dict[str, Any],
    fact_tables: list[dict[str, Any]],
    dim_tables: list[dict[str, Any]],
    summary_tables: list[dict[str, Any]],
) -> list[str]:
    notes = [
        "table choices are provider-driven; validate provider metadata freshness before production use",
        "dimension joins must be checked for one-to-one keys to avoid metric inflation",
    ]
    if not dim_tables:
        notes.append(
            "no DIM table matched requested semantic dimensions; dimensions may be carried by fact/summary fields"
        )
    if not fact_tables:
        notes.append("no fact table matched requested metrics; fallback fact table is planned")
    if summary_tables and summary_tables[0].get("reuse"):
        notes.append("DWS reuse selected; ADS SQL should not regenerate the reused DWS table")
    if reuse_decision.get("risk_notes"):
        notes.extend(reuse_decision["risk_notes"])
    return notes
