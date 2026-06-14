from __future__ import annotations

import os
from typing import Any

from dw_agent.metadata import get_metadata_provider
from dw_agent.nodes.decide_table_reuse import infer_business_process
from dw_agent.state import AgentState
from dw_agent.tools.datahub_mcp_tool import (
    get_datahub_dataset_schema,
    get_datahub_lineage,
    get_datahub_ownership,
    get_datahub_tags_and_terms,
    search_datahub_assets,
)


def tool_router(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    provider = get_metadata_provider({"knowledge_base_path": state.get("knowledge_base_path")})
    business_process = infer_business_process(parsed)

    calls: list[dict[str, Any]] = [
        {
            "tool": "search_dimensions",
            "arguments": {"semantic_dimensions": parsed.get("dimensions", [])},
        },
        {
            "tool": "search_facts",
            "arguments": {"metrics": parsed.get("metrics", []), "business_process": business_process},
        },
        {
            "tool": "search_summaries",
            "arguments": {
                "dimensions": parsed.get("dimensions", []),
                "metrics": parsed.get("metrics", []),
                "grain": parsed.get("granularity"),
                "business_process": business_process,
            },
        },
        {
            "tool": "search_tables",
            "arguments": {"business_process": business_process, "top_k": 5},
        },
    ]

    results: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []
    for call in calls:
        tool = str(call["tool"])
        arguments = dict(call["arguments"])
        try:
            results[tool] = _call_provider_tool(provider, tool, arguments)
        except Exception as exc:
            errors.append({"tool": tool, "arguments": arguments, "error": f"{type(exc).__name__}: {exc}"})

    datahub_calls, datahub_results, datahub_errors = _run_datahub_tools(state)
    calls.extend(datahub_calls)
    results.update(datahub_results)
    errors.extend(datahub_errors)

    trace = {
        "tool": "tool_router",
        "input": {"provider": provider.__class__.__name__, "planned_tools": [call["tool"] for call in calls]},
        "output": {
            "result_counts": {name: _result_count(value) for name, value in results.items()},
            "error_count": len(errors),
        },
    }
    return {
        **state,
        "tool_calls": calls,
        "tool_results": results,
        "tool_errors": errors,
        "tool_trace": [*state.get("tool_trace", []), trace],
    }


def _call_provider_tool(provider, tool: str, arguments: dict[str, Any]):
    if tool == "search_dimensions":
        return provider.search_dimensions(arguments["semantic_dimensions"])
    if tool == "search_facts":
        return provider.search_facts(arguments["metrics"], arguments.get("business_process"))
    if tool == "search_summaries":
        return provider.search_summaries(
            arguments["dimensions"],
            arguments["metrics"],
            arguments.get("grain"),
            arguments.get("business_process"),
        )
    if tool == "search_tables":
        return provider.search_tables(
            business_process=arguments.get("business_process"),
            top_k=arguments.get("top_k", 5),
        )
    raise ValueError(f"Unsupported tool: {tool}")


def _run_datahub_tools(state: AgentState) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    if not _needs_datahub(state):
        return [], {}, []

    parsed = state["parsed"]
    query = " ".join(
        str(item)
        for item in [
            state.get("requirement", ""),
            parsed.get("business_theme", ""),
            *parsed.get("metrics", []),
            *parsed.get("dimensions", []),
        ]
        if item
    )
    calls = [
        {
            "tool": "search_datahub_assets",
            "arguments": {"query": query, "entity_types": ["dataset"], "limit": 5},
        }
    ]
    results: dict[str, Any] = {}
    errors: list[dict[str, Any]] = []

    search_result = search_datahub_assets(query, entity_types=["dataset"], limit=5)
    results["search_datahub_assets"] = search_result
    if search_result.get("errors"):
        errors.append(
            {"tool": "search_datahub_assets", "arguments": {"query": query}, "error": search_result["errors"]}
        )

    contexts = []
    for asset in search_result.get("assets", [])[:2]:
        urn = asset.get("urn")
        if not urn:
            continue
        calls.extend(
            [
                {"tool": "get_datahub_dataset_schema", "arguments": {"dataset_urn": urn}},
                {"tool": "get_datahub_lineage", "arguments": {"dataset_urn": urn, "direction": "upstream", "depth": 1}},
                {"tool": "get_datahub_ownership", "arguments": {"dataset_urn": urn}},
                {"tool": "get_datahub_tags_and_terms", "arguments": {"dataset_urn": urn}},
            ]
        )
        schema = get_datahub_dataset_schema(urn)
        lineage = get_datahub_lineage(urn, direction="upstream", depth=1)
        ownership = get_datahub_ownership(urn)
        tags_terms = get_datahub_tags_and_terms(urn)
        contexts.append(
            {
                "asset": asset,
                "schema": schema,
                "lineage": lineage,
                "ownership": ownership,
                "tags_and_terms": tags_terms,
            }
        )
        for tool_result in [schema, lineage, ownership, tags_terms]:
            if tool_result.get("errors"):
                errors.append(
                    {
                        "tool": tool_result.get("tool"),
                        "arguments": {"dataset_urn": urn},
                        "error": tool_result["errors"],
                    }
                )
    results["datahub_dataset_context"] = contexts
    return calls, results, errors


def _needs_datahub(state: AgentState) -> bool:
    if os.getenv("WAREHOUSE_METADATA_PROVIDER", "").lower() in {"datahub_mcp", "datahub"}:
        return True
    plan_tools = set(state.get("agent_plan", {}).get("tools_needed", []))
    if any(tool.startswith("search_datahub") or tool.startswith("get_datahub") for tool in plan_tools):
        return True
    provider_name = str(state.get("agent_plan", {}).get("metadata_provider", ""))
    return provider_name == "datahub_mcp"


def _result_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if value is None:
        return 0
    return 1
