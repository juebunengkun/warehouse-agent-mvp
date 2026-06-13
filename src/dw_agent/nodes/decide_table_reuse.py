from __future__ import annotations

from dw_agent.mcp_client import call_mcp_tools
from dw_agent.metadata import field_names, grain_fields
from dw_agent.nodes.common import group_fields, metric_columns
from dw_agent.state import AgentState


def infer_business_process(parsed: dict) -> str:
    metrics = set(parsed.get("metrics", []))
    dimensions = set(parsed.get("dimensions", []))
    if metrics & {"曝光UV", "点击UV"} or {"渠道类型", "新老用户", "会员等级"} & dimensions:
        return "channel_operation"
    if metrics & {"销售额", "订单数", "支付用户数", "支付订单数", "GMV", "实付金额", "退款金额"}:
        return "trade_order"
    return "general_report"


def decide_table_reuse(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    candidates = [
        table for table in state.get("metadata_candidates", []) if str(table.get("layer", "")).upper() in {"DWS", "ADS"}
    ]

    schemas = []
    if candidates:
        outputs = call_mcp_tools(
            [("get_table_schema_tool", {"table_name": table["name"]}) for table in candidates if table.get("name")]
        )
        schemas = [schema for schema in outputs if isinstance(schema, dict) and schema.get("matched")]

    required_dims = set(group_fields(parsed))
    required_metrics = {field for _, field, _, _ in metric_columns(parsed.get("metrics", []))}
    required_fields = required_dims | required_metrics
    expected_process = infer_business_process(parsed)
    required_refresh_time = _required_sla_time(parsed.get("refresh_cycle", ""))

    best = None
    for schema in schemas:
        table_fields = field_names(schema)
        table_grain = grain_fields(schema)
        covered = required_fields & table_fields
        missing = required_fields - table_fields
        required_metric_missing = required_metrics - table_fields
        hard_checks = {
            "field_covered": not missing,
            "grain_matched": required_dims == table_grain,
            "metric_semantics_matched": not required_metric_missing,
            "business_process_matched": schema.get("business_process") in {expected_process, "general_report"},
            "update_mode_supported": schema.get("update_mode") == "incremental",
            "partition_available": bool(schema.get("partition_key")),
            "certified": bool(schema.get("certified")),
            "sla_satisfied": _sla_satisfied(schema.get("sla_time"), required_refresh_time),
            "one_to_many_join_risk": False,
        }
        risk_notes = _risk_notes(hard_checks, schema, required_dims, table_grain, missing)

        score = len(covered) * 2
        if schema.get("layer") == "DWS":
            score += 6
        if schema.get("layer") == "ADS":
            score += 2
        if hard_checks["certified"]:
            score += 4
        if hard_checks["grain_matched"]:
            score += 8
        if hard_checks["business_process_matched"]:
            score += 5
        if hard_checks["sla_satisfied"]:
            score += 2
        if all(hard_checks.values()):
            score += 10
        candidate = {
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
            "risk_notes": risk_notes,
            "description": schema.get("description", ""),
        }
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
            "reason": "已有认证 DWS 表覆盖字段、粒度、业务过程和分区要求，可复用汇总层并生成 ADS。",
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
    schema: dict,
    required_dims: set[str],
    table_grain: set[str],
    missing: set[str],
) -> list[str]:
    notes = []
    if missing:
        notes.append(f"字段缺失：{', '.join(sorted(missing))}。")
    if required_dims != table_grain:
        notes.append(
            "粒度不完全一致："
            f"需求粒度={', '.join(sorted(required_dims)) or '无'}；"
            f"候选粒度={', '.join(sorted(table_grain)) or schema.get('grain', '未知')}。"
        )
    if not hard_checks["certified"]:
        notes.append("候选表未认证，复用前需要人工确认。")
    if not hard_checks["sla_satisfied"]:
        notes.append("候选表 SLA 晚于报表要求。")
    if schema.get("layer") == "ADS":
        notes.append("ADS 更偏应用消费层，优先级低于公共 DWS。")
    return notes
