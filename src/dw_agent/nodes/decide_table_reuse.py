from __future__ import annotations

from dw_agent.mcp_client import call_mcp_tools
from dw_agent.nodes.common import group_fields, metric_columns
from dw_agent.state import AgentState


def decide_table_reuse(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    candidates = [
        table
        for table in state.get("metadata_candidates", [])
        if str(table.get("layer", "")).upper() in {"DWS", "ADS"}
    ]

    schemas = []
    if candidates:
        outputs = call_mcp_tools(
            [
                ("get_table_schema_tool", {"table_name": table["name"]})
                for table in candidates
                if table.get("name")
            ]
        )
        schemas = [schema for schema in outputs if isinstance(schema, dict) and schema.get("matched")]

    required_dims = set(group_fields(parsed))
    required_metrics = {field for _, field, _, _ in metric_columns(parsed.get("metrics", []))}
    required_fields = required_dims | required_metrics

    best = None
    for schema in schemas:
        field_names = {field.get("name") for field in schema.get("fields", [])}
        covered = required_fields & field_names
        missing = required_fields - field_names
        score = len(covered) * 2
        if schema.get("layer") == "DWS":
            score += 2
        if not missing:
            score += 10
        candidate = {
            "table": schema.get("name"),
            "layer": schema.get("layer"),
            "score": score,
            "covered_fields": sorted(covered),
            "missing_fields": sorted(missing),
            "grain": schema.get("grain", ""),
            "description": schema.get("description", ""),
        }
        if best is None or candidate["score"] > best["score"]:
            best = candidate

    if best and not best["missing_fields"] and best["layer"] == "DWS":
        decision = {
            "decision": "reuse_existing_dws",
            "table": best["table"],
            "reason": "已有 DWS 表覆盖所需维度和指标，可复用汇总层并生成 ADS。",
            **best,
        }
    else:
        decision = {
            "decision": "create_new_tables",
            "table": best.get("table") if best else None,
            "reason": "未找到完全覆盖当前指标和粒度的 DWS 表，建议生成新的 DWS/ADS 初稿。",
            "best_candidate": best,
        }

    trace = [
        *state.get("tool_trace", []),
        {
            "tool": "reuse_decision",
            "input": {
                "required_fields": sorted(required_fields),
                "candidate_count": len(candidates),
            },
            "output": decision,
        },
    ]
    return {**state, "reuse_decision": decision, "tool_trace": trace}
