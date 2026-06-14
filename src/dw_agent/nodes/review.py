from __future__ import annotations

from typing import Any

from dw_agent.nodes.common import METRIC_COLUMNS, markdown_table
from dw_agent.state import AgentState


def review_outputs(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    metrics = parsed.get("metrics", [])
    dimensions = parsed.get("dimensions", [])
    matched_metrics = [metric for metric in metrics if metric in METRIC_COLUMNS]
    missing_metrics = [metric for metric in metrics if metric not in METRIC_COLUMNS]

    summary = [
        "## Executive Review",
        "",
        f"- Requirement parser source: `{parsed.get('parser_source', 'unknown')}`.",
        f"- Matched metric definitions: {', '.join(matched_metrics) if matched_metrics else 'none'}.",
        f"- Missing metric definitions: {', '.join(missing_metrics) if missing_metrics else 'none'}.",
        f"- Requested grain: {parsed.get('granularity', 'unknown')}.",
        f"- Dimensions: {', '.join(dimensions) if dimensions else 'none'}.",
        _llm_finding(state.get("llm_diagnostics", {})),
    ]

    review = "\n".join(summary)
    review += _agent_plan_review(state.get("agent_plan", {}))
    review += _clarification_review(state.get("clarification", {}))
    review += _tool_calls_review(
        state.get("tool_calls", []),
        state.get("tool_results", {}),
        state.get("tool_errors", []),
    )
    review += _datahub_context_review(
        state.get("tool_calls", []),
        state.get("tool_results", {}),
        state.get("tool_errors", []),
    )
    review += _strategy_review(state.get("modeling_strategy", {}))
    review += _reuse_review(state.get("reuse_decision", {}))
    review += _sql_validation_review(state.get("sql_validation", {}))
    review += _sql_style_review(state.get("sql_style_review", {}))
    review += _sql_preview_review(state.get("sql_preview", {}))
    review += _verification_review(state.get("verification_result", {}))
    review += _tool_trace_review(state.get("tool_trace", []))
    review += _memory_review(state.get("memory_context", []))
    review += _mvp_limitations_review()

    final_report = "\n\n".join(
        [
            "# Data Warehouse Agent Output Report",
            state.get("modeling_plan", ""),
            "## DDL\n\n```sql\n" + state.get("ddl", "") + "\n```",
            "## ETL SQL\n\n```sql\n" + state.get("etl_sql", "") + "\n```",
            state.get("dqc_rules", ""),
            review,
        ]
    )
    return {**state, "review": review, "final_report": final_report}


def _llm_finding(diagnostics: dict[str, Any]) -> str:
    if not diagnostics:
        return "- LLM diagnostics: not recorded."
    if diagnostics.get("status") == "success":
        return f"- LLM diagnostics: requirement parsing succeeded with model `{diagnostics.get('model')}`."
    if diagnostics.get("status") == "failed":
        return (
            "- LLM diagnostics: call failed and the agent fell back to rule parsing "
            f"({diagnostics.get('error_type', 'unknown error')})."
        )
    if diagnostics.get("enabled") and diagnostics.get("has_api_key"):
        return f"- LLM diagnostics: model `{diagnostics.get('model')}` configured but not used in this run."
    return "- LLM diagnostics: LLM unavailable or disabled; rule parsing was used."


def _agent_plan_review(plan: dict[str, Any]) -> str:
    if not plan:
        return ""
    lines = [
        "\n\n## Agent Plan",
        "",
        f"- Goal: {plan.get('goal', '')}",
        f"- Metadata provider: `{plan.get('metadata_provider', 'unknown')}`",
        f"- Need clarification: {plan.get('need_clarification', False)}",
        f"- Tools needed: {', '.join(plan.get('tools_needed', [])) or 'none'}",
        "- Steps:",
    ]
    for item in plan.get("steps", []):
        lines.append(f"  - `{item.get('step')}`: {item.get('purpose')}")
    if plan.get("risk_notes"):
        lines.append("- Risk notes:")
        lines.extend(f"  - {note}" for note in plan.get("risk_notes", []))
    return "\n".join(lines)


def _clarification_review(clarification: dict[str, Any]) -> str:
    if not clarification:
        return ""
    lines = [
        "\n\n## Clarification",
        "",
        f"- Need clarification: {clarification.get('need_clarification', False)}",
        f"- Blocking for production: {clarification.get('blocking', False)}",
        f"- Human review required: {clarification.get('human_review_required', False)}",
        "- Questions:",
    ]
    questions = clarification.get("questions", [])
    lines.extend(f"  - {question}" for question in questions) if questions else lines.append("  - none")
    lines.append("- Default assumptions:")
    assumptions = clarification.get("default_assumptions", [])
    lines.extend(f"  - {assumption}" for assumption in assumptions) if assumptions else lines.append("  - none")
    return "\n".join(lines)


def _tool_calls_review(
    tool_calls: list[dict[str, Any]], tool_results: dict[str, Any], tool_errors: list[dict[str, Any]]
) -> str:
    if not tool_calls and not tool_results and not tool_errors:
        return ""
    lines = ["\n\n## Tool Calls", ""]
    if tool_calls:
        lines.append("- Calls:")
        lines.extend(f"  - `{item.get('tool')}` args={_compact_dict(item.get('arguments', {}))}" for item in tool_calls)
    if tool_results:
        lines.append("- Results:")
        lines.extend(f"  - `{name}`: {_result_summary(value)}" for name, value in tool_results.items())
    if tool_errors:
        lines.append("- Errors:")
        lines.extend(f"  - `{item.get('tool')}`: {item.get('error')}" for item in tool_errors)
    return "\n".join(lines)


def _datahub_context_review(
    tool_calls: list[dict[str, Any]], tool_results: dict[str, Any], tool_errors: list[dict[str, Any]]
) -> str:
    datahub_calls = [item for item in tool_calls if "datahub" in str(item.get("tool", "")).lower()]
    search_result = tool_results.get("search_datahub_assets", {})
    contexts = tool_results.get("datahub_dataset_context", [])
    datahub_errors = [item for item in tool_errors if "datahub" in str(item.get("tool", "")).lower()]

    lines = ["\n\n## DataHub MCP Context", ""]
    if not datahub_calls and not search_result and not contexts:
        lines.extend(
            [
                "- Status: skipped.",
                "- Reason: DataHub MCP was not requested; keep `DATAHUB_MCP_ENABLED=false` or use another metadata provider.",
            ]
        )
        return "\n".join(lines)

    if isinstance(search_result, dict) and search_result.get("skipped"):
        reason = "; ".join(str(item) for item in search_result.get("warnings", [])) or "DataHub MCP is disabled."
        lines.extend(["- Status: skipped.", f"- Reason: {_safe_text(reason)}"])
        return "\n".join(lines)

    status = "queried" if not datahub_errors else "queried_with_errors"
    lines.append(f"- Status: {status}.")
    if datahub_calls:
        called_tools = ", ".join(f"`{item.get('tool')}`" for item in datahub_calls)
        lines.append(f"- Called tools: {called_tools}.")

    assets = search_result.get("assets", []) if isinstance(search_result, dict) else []
    if assets:
        rows = [
            [
                _safe_text(asset.get("name", "")),
                _safe_text(asset.get("platform", "")),
                _safe_text(asset.get("owner", "")),
                ", ".join(asset.get("tags", [])[:3]),
                _short_urn(str(asset.get("urn", ""))),
            ]
            for asset in assets[:5]
        ]
        lines.append("\n### Matched Assets\n")
        lines.append(markdown_table(["Asset", "Platform", "Owner", "Tags", "URN"], rows))
    else:
        lines.append("- Matched assets: none.")

    if contexts:
        rows = []
        for item in contexts:
            asset = item.get("asset", {})
            schema = item.get("schema", {})
            lineage = item.get("lineage", {})
            ownership = item.get("ownership", {})
            tags_terms = item.get("tags_and_terms", {})
            owners = ", ".join(owner.get("name", "") for owner in ownership.get("owners", []) if owner.get("name"))
            tags = ", ".join([*tags_terms.get("tags", [])[:2], *tags_terms.get("glossary_terms", [])[:2]])
            rows.append(
                [
                    _safe_text(asset.get("name", "")),
                    str(len(schema.get("fields", []))),
                    _safe_text(owners or asset.get("owner", "")),
                    _safe_text(tags),
                    str(len(lineage.get("lineage", []))),
                ]
            )
        lines.append("\n### Dataset Details\n")
        lines.append(markdown_table(["Asset", "Fields", "Owner", "Tags / Terms", "Upstream Count"], rows))

    if datahub_errors:
        lines.append("- DataHub tool errors:")
        lines.extend(f"  - `{item.get('tool')}`: {_safe_text(str(item.get('error')))}" for item in datahub_errors)

    lines.append(
        "- Modeling impact: DataHub metadata can improve table discovery, owner/trust signals, schema checks, and lineage context; metric semantics and final reuse decisions still need validation."
    )
    return "\n".join(lines)


def _strategy_review(strategy: dict[str, Any]) -> str:
    if not strategy:
        return ""
    sections = ["\n\n## Modeling Strategy", "", f"- Business process: {strategy.get('business_process', 'unknown')}"]
    for title, key in [
        ("Fact Tables", "fact_tables"),
        ("Dimension Tables", "dim_tables"),
        ("Summary Tables", "summary_tables"),
        ("Application Tables", "application_tables"),
    ]:
        rows = [
            [
                table.get("name", ""),
                table.get("layer", ""),
                table.get("table_type", ""),
                table.get("grain", ""),
                table.get("update_mode", ""),
                table.get("reason", ""),
            ]
            for table in strategy.get(key, [])
        ]
        sections.append(f"\n### {title}\n")
        sections.append(
            markdown_table(["Table", "Layer", "Type", "Grain", "Update Mode", "Reason"], rows) if rows else "None."
        )

    joins = strategy.get("join_plan", [])
    sections.append("\n### Join Plan\n")
    if joins:
        rows = [
            [
                item.get("left_table", ""),
                item.get("right_table", ""),
                item.get("join_type", ""),
                ", ".join(item.get("join_keys", [])),
                item.get("partition_condition", ""),
            ]
            for item in joins
        ]
        sections.append(markdown_table(["Left Table", "Right Table", "Join Type", "Keys", "Partition"], rows))
    else:
        sections.append("No additional dimension joins are required.")

    sections.append("\n### Dependency Plan\n")
    dependencies = strategy.get("dependency_plan", [])
    sections.append(
        "\n".join(f"- {item}" for item in dependencies) if dependencies else "- No dependency plan generated."
    )
    return "\n".join(sections)


def _reuse_review(reuse_decision: dict[str, Any]) -> str:
    if not reuse_decision:
        return ""
    risk_notes = reuse_decision.get("risk_notes", [])
    return f"""

## Table Reuse Decision
- Decision: {reuse_decision.get("decision")}
- Reused table: {reuse_decision.get("table") or "none"}
- Reason: {reuse_decision.get("reason")}
- Hard checks: `{reuse_decision.get("hard_checks", {})}`
- Risks: {", ".join(risk_notes) if risk_notes else "none"}
"""


def _sql_validation_review(validation: dict[str, Any]) -> str:
    if not validation:
        return ""
    lines = ["\n\n## SQL Validation", "", f"- Passed: {validation.get('passed', False)}"]
    lines.extend(f"- Error: {item}" for item in validation.get("errors", []))
    lines.extend(f"- Warning: {item}" for item in validation.get("warnings", []))
    if len(lines) == 3:
        lines.append("- No blocking issue detected.")
    return "\n".join(lines)


def _sql_style_review(style_review: dict[str, Any]) -> str:
    if not style_review:
        return ""
    lines = ["\n\n## SQL Style Review", "", f"- Passed: {style_review.get('passed', False)}"]
    issues = style_review.get("issues", [])
    if issues:
        lines.extend(f"- {item.get('level')} `{item.get('rule')}`: {item.get('message')}" for item in issues)
    else:
        lines.append("- No SQL style issue detected.")
    return "\n".join(lines)


def _sql_preview_review(preview: dict[str, Any]) -> str:
    if not preview:
        return ""
    lines = [
        "\n\n## SQL Preview",
        "",
        f"- Preview available: {preview.get('preview_available', False)}",
        f"- Passed: {preview.get('passed', False)}",
        f"- Row count: {preview.get('row_count', 0)}",
    ]
    if preview.get("reason"):
        lines.append(f"- Reason: {preview.get('reason')}")
    lines.extend(f"- Warning: {item}" for item in preview.get("warnings", []))
    lines.extend(f"- Error: {item}" for item in preview.get("errors", []))
    return "\n".join(lines)


def _verification_review(verification: dict[str, Any]) -> str:
    if not verification:
        return ""
    lines = [
        "\n\n## Verification Result",
        "",
        f"- Passed: {verification.get('passed', False)}",
        f"- Need rewrite: {verification.get('need_rewrite', False)}",
        f"- Need human review: {verification.get('need_human_review', False)}",
        f"- Suggested next action: {verification.get('suggested_next_action', '')}",
    ]
    lines.extend(f"- Blocking issue: {item}" for item in verification.get("blocking_issues", []))
    lines.extend(f"- Warning: {item}" for item in verification.get("warnings", []))
    return "\n".join(lines)


def _tool_trace_review(tool_trace: list[dict[str, Any]]) -> str:
    if not tool_trace:
        return ""
    lines = ["\n\n## Agent Trace", ""]
    lines.extend(
        f"- {index}. `{item.get('tool')}` -> {item.get('output')}" for index, item in enumerate(tool_trace, start=1)
    )
    return "\n".join(lines)


def _memory_review(memory_context: list[dict[str, Any]]) -> str:
    if not memory_context:
        return ""
    lines = ["\n\n## Memory Context", ""]
    lines.extend(
        f"- Session #{item['id']}: score={item.get('score')}, requirement={item.get('requirement')}"
        for item in memory_context
    )
    return "\n".join(lines)


def _mvp_limitations_review() -> str:
    return """

## MVP Limitations
- This is a Controlled Data Warehouse Agent MVP, not a production autonomous agent.
- It does not execute production write SQL or deploy scheduler jobs.
- DuckDB SQL preview is read-only and SELECT-only.
- Metric platform, permission platform, approval workflow, lineage, and production dry-run are not connected yet.
- Key metric semantics and reusable-table decisions still require human review before production use.
"""


def _compact_dict(value: dict[str, Any]) -> str:
    return ", ".join(f"{key}={val}" for key, val in value.items())


def _result_summary(value: Any) -> str:
    if isinstance(value, list):
        names = [str(item.get("name")) for item in value[:3] if isinstance(item, dict) and item.get("name")]
        suffix = f" ({', '.join(names)})" if names else ""
        return f"{len(value)} result(s){suffix}"
    if isinstance(value, dict):
        return f"{len(value)} key(s)"
    return str(value)


def _short_urn(value: str) -> str:
    if len(value) <= 72:
        return _safe_text(value)
    return _safe_text(value[:69] + "...")


def _safe_text(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ").replace("\r", " ")
