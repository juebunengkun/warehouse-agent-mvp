from __future__ import annotations

from typing import Any

from dw_agent.metadata import get_metadata_provider
from dw_agent.nodes.decide_table_reuse import infer_business_process
from dw_agent.state import AgentState


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


def _result_count(value: Any) -> int:
    if isinstance(value, list):
        return len(value)
    if value is None:
        return 0
    return 1
