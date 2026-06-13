from __future__ import annotations

from typing import Any

from dw_agent.metadata import (
    field_names,
    get_metadata_provider,
    grain_fields,
    metric_fields,
    metric_source_fields,
    semantic_dimension_fields,
)
from dw_agent.nodes.common import group_fields
from dw_agent.state import AgentState


def infer_business_process(parsed: dict[str, Any]) -> str:
    dimension_fields = semantic_dimension_fields(parsed.get("dimensions", []))
    metric_semantics = metric_fields(parsed.get("metrics", [])) | metric_source_fields(parsed.get("metrics", []))
    if {"exposure_uv", "click_uv", "exposure_user_id", "click_user_id"} & metric_semantics:
        return "channel_operation"
    if {"channel_type", "user_type", "member_level"} & dimension_fields:
        return "channel_operation"
    if {"sales_amount", "pay_amount", "gmv_amount", "refund_amount", "order_id", "order_count"} & metric_semantics:
        return "trade_order"
    return "general_report"


def decide_table_reuse(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    provider = get_metadata_provider({"knowledge_base_path": state.get("knowledge_base_path")})
    required_dims = set(group_fields(parsed))
    required_metrics = metric_fields(parsed.get("metrics", []))
    required_fields = required_dims | required_metrics
    expected_process = infer_business_process(parsed)
    required_refresh_time = _required_sla_time(parsed.get("refresh_cycle", ""))

    candidates = [
        *provider.search_summaries(
            parsed.get("dimensions", []),
            parsed.get("metrics", []),
            required_dims,
            expected_process,
        ),
        *provider.search_tables(
            layer="ADS",
            table_type="application_report",
            business_process=expected_process,
            fields=required_fields,
            grain=required_dims,
            top_k=3,
        ),
    ]

    best = None
    for schema in candidates:
        candidate = _evaluate_candidate(schema, required_fields, required_metrics, required_dims, expected_process)
        candidate["hard_checks"]["sla_satisfied"] = _sla_satisfied(schema.get("sla_time"), required_refresh_time)
        candidate["risk_notes"] = _risk_notes(
            candidate["hard_checks"], schema, required_dims, candidate["missing_fields"]
        )
        if best is None or candidate["score"] > best["score"]:
            best = candidate

    can_reuse = bool(
        best
        and best["layer"] == "DWS"
        and best["hard_checks"]["field_covered"]
        and best["hard_checks"]["grain_matched"]
        and best["hard_checks"]["metric_semantics_matched"]
        and best["hard_checks"]["business_process_matched"]
        and best["hard_checks"]["partition_available"]
    )
    if can_reuse and best is not None:
        decision = {
            "decision": "reuse_existing_dws",
            "table": best["table"],
            "reason": "metadata hard checks passed; reuse public DWS and generate ADS only",
            **best,
        }
    else:
        decision = {
            "decision": "create_new_tables",
            "table": best.get("table") if best else None,
            "reason": "no DWS candidate satisfied all required hard checks",
            "hard_checks": best.get("hard_checks") if best else _empty_hard_checks(),
            "score": best.get("score", 0) if best else 0,
            "risk_notes": (
                best.get("risk_notes", ["no reusable DWS candidate found"])
                if best
                else ["no reusable DWS candidate found"]
            ),
            "best_candidate": best,
        }

    trace = [
        *state.get("tool_trace", []),
        {
            "tool": "reuse_decision",
            "input": {
                "required_fields": sorted(required_fields),
                "candidate_count": len(candidates),
                "provider": provider.__class__.__name__,
            },
            "output": decision,
        },
    ]
    return {**state, "reuse_decision": decision, "tool_trace": trace}


def _evaluate_candidate(
    schema: dict[str, Any],
    required_fields: set[str],
    required_metrics: set[str],
    required_dims: set[str],
    expected_process: str,
) -> dict[str, Any]:
    table_fields = field_names(schema)
    table_grain = grain_fields(schema)
    covered = required_fields & table_fields
    missing = required_fields - table_fields
    required_metric_missing = required_metrics - table_fields
    grain_matched = bool(required_dims == table_grain or (required_dims and required_dims.issubset(table_grain)))
    business_process_matched = schema.get("business_process") in {expected_process, "general_report"}

    hard_checks = {
        "field_covered": not missing,
        "grain_matched": grain_matched,
        "metric_semantics_matched": not required_metric_missing,
        "business_process_matched": business_process_matched,
        "partition_available": bool(schema.get("partition_key")),
        "certified": bool(schema.get("certified")),
        "sla_satisfied": True,
    }

    score = int(schema.get("score") or 0)
    if schema.get("layer") == "DWS":
        score += 20
    if schema.get("layer") == "ADS":
        score += 4
    if hard_checks["field_covered"]:
        score += 18
    if hard_checks["grain_matched"]:
        score += 16
    if hard_checks["metric_semantics_matched"]:
        score += 10
    if hard_checks["business_process_matched"]:
        score += 10
    if hard_checks["partition_available"]:
        score += 5
    if hard_checks["certified"]:
        score += 5

    return {
        "table": schema.get("name"),
        "layer": schema.get("layer"),
        "score": score,
        "covered_fields": sorted(covered),
        "missing_fields": sorted(missing),
        "grain": schema.get("grain", ""),
        "business_process": schema.get("business_process", ""),
        "update_mode": schema.get("update_mode", ""),
        "partition_key": schema.get("partition_key", ""),
        "certified": schema.get("certified", False),
        "sla_time": schema.get("sla_time", ""),
        "hard_checks": hard_checks,
        "description": schema.get("description", ""),
    }


def _empty_hard_checks() -> dict[str, bool]:
    return {
        "field_covered": False,
        "grain_matched": False,
        "metric_semantics_matched": False,
        "business_process_matched": False,
        "partition_available": False,
        "certified": False,
        "sla_satisfied": False,
    }


def _required_sla_time(refresh_cycle: str) -> str | None:
    if "08:30" in refresh_cycle:
        return "08:30"
    if "09:00" in refresh_cycle:
        return "09:00"
    return None


def _sla_satisfied(table_sla: str | None, required_sla: str | None) -> bool:
    if not required_sla:
        return True
    if not table_sla:
        return False
    return table_sla <= required_sla


def _risk_notes(
    hard_checks: dict[str, bool],
    schema: dict[str, Any],
    required_dims: set[str],
    missing: list[str],
) -> list[str]:
    notes = []
    if missing:
        notes.append(f"missing fields: {', '.join(missing)}")
    if not hard_checks["grain_matched"]:
        notes.append(
            f"grain mismatch: requested {', '.join(sorted(required_dims))}, candidate {schema.get('grain', '')}"
        )
    if not hard_checks["metric_semantics_matched"]:
        notes.append("metric aliases are not fully covered by candidate table")
    if not hard_checks["business_process_matched"]:
        notes.append("business process differs from parsed requirement")
    if not hard_checks["certified"]:
        notes.append("candidate table is not certified; manual review required")
    if not hard_checks["sla_satisfied"]:
        notes.append("candidate table SLA is later than report requirement")
    if schema.get("layer") == "ADS":
        notes.append("ADS is application-specific and ranks below reusable DWS")
    return notes
