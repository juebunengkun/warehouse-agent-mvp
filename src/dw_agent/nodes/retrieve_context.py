from __future__ import annotations

import os

from dw_agent.mcp_client import call_mcp_tools
from dw_agent.metadata import get_metadata_provider
from dw_agent.state import AgentState


def retrieve_context(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    tool_trace = [*state.get("tool_trace", [])]

    metrics = " ".join(parsed.get("metrics", []))
    dimensions = " ".join(parsed.get("dimensions", []))
    theme = parsed.get("business_theme", "")
    use_provider_metadata = os.getenv("WAREHOUSE_METADATA_PROVIDER", "local_json").lower() in {
        "information_schema",
        "infoschema",
        "database",
    }

    calls = [
        ("search_warehouse_docs_tool", {"query": f"ODS DWD DWS ADS naming partition grain {theme}", "top_k": 4}),
        ("search_warehouse_docs_tool", {"query": f"{metrics} metric definition source fields", "top_k": 4}),
        ("search_warehouse_docs_tool", {"query": f"{theme} {metrics} {dimensions} table schema fields", "top_k": 5}),
        (
            "search_warehouse_docs_tool",
            {"query": f"{metrics} {dimensions} DQC null unique volatility partition", "top_k": 4},
        ),
        *[("get_metric_definition_tool", {"metric_name": metric}) for metric in parsed.get("metrics", [])],
    ]
    if not use_provider_metadata:
        calls.append(("list_tables_tool", {"layer": None}))

    outputs = call_mcp_tools(calls)

    standards, metric_docs, table_docs, dqc_docs = outputs[:4]
    metric_context = outputs[4 : 4 + len(parsed.get("metrics", []))]
    if use_provider_metadata:
        metadata_candidates = _provider_metadata_candidates(state)
        tool_trace.append(
            {
                "tool": "metadata_provider.search_tables",
                "input": {"provider": os.getenv("WAREHOUSE_METADATA_PROVIDER")},
                "output": _summarize_output(metadata_candidates),
            }
        )
    else:
        metadata_candidates = outputs[-1]

    for (tool_name, arguments), output in zip(calls, outputs, strict=False):
        tool_trace.append(
            {
                "tool": f"mcp.{tool_name}",
                "input": arguments,
                "output": _summarize_output(output),
            }
        )

    retrievals = {
        "warehouse_layering_and_naming": standards,
        "metric_definitions": metric_docs,
        "historical_table_schemas": table_docs,
        "dqc_templates": dqc_docs,
    }

    return {
        **state,
        "retrievals": retrievals,
        "metric_context": metric_context,
        "metadata_candidates": metadata_candidates,
        "tool_trace": tool_trace,
    }


def _provider_metadata_candidates(state: AgentState) -> list[dict]:
    provider = get_metadata_provider({"knowledge_base_path": state.get("knowledge_base_path")})
    return [
        {
            "name": table.get("name"),
            "layer": table.get("layer"),
            "description": table.get("description"),
            "field_count": len(table.get("fields", [])),
        }
        for table in provider.search_tables(top_k=50)
    ]


def _summarize_output(output):
    if isinstance(output, list):
        return {"count": len(output), "preview": output[:2]}
    if isinstance(output, dict):
        return {key: output[key] for key in list(output)[:6]}
    return output
