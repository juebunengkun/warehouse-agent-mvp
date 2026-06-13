from __future__ import annotations

from dw_agent.mcp_client import call_mcp_tools
from dw_agent.state import AgentState


def retrieve_context(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    tool_trace = [*state.get("tool_trace", [])]

    metrics = " ".join(parsed.get("metrics", []))
    dimensions = " ".join(parsed.get("dimensions", []))
    theme = parsed.get("business_theme", "")

    calls = [
        ("search_warehouse_docs_tool", {"query": f"ODS DWD DWS ADS 命名 分区 粒度 {theme}", "top_k": 4}),
        ("search_warehouse_docs_tool", {"query": f"{metrics} 指标 口径 计算 依赖字段", "top_k": 4}),
        ("search_warehouse_docs_tool", {"query": f"{theme} {metrics} {dimensions} 表结构 字段 明细 汇总", "top_k": 5}),
        ("search_warehouse_docs_tool", {"query": f"{metrics} {dimensions} DQC 非空 唯一 波动 分区", "top_k": 4}),
        *[
            ("get_metric_definition_tool", {"metric_name": metric})
            for metric in parsed.get("metrics", [])
        ],
        ("list_tables_tool", {"layer": None}),
    ]
    outputs = call_mcp_tools(calls)

    standards, metric_docs, table_docs, dqc_docs = outputs[:4]
    metric_context = outputs[4 : 4 + len(parsed.get("metrics", []))]
    metadata_candidates = outputs[-1]

    for (tool_name, arguments), output in zip(calls, outputs):
        tool_trace.append(
            {
                "tool": f"mcp.{tool_name}",
                "input": arguments,
                "output": _summarize_output(output),
            }
        )

    retrievals = {
        "数仓分层与命名规范": standards,
        "指标口径": metric_docs,
        "历史表结构": table_docs,
        "DQC 模板": dqc_docs,
    }

    return {
        **state,
        "retrievals": retrievals,
        "metric_context": metric_context,
        "metadata_candidates": metadata_candidates,
        "tool_trace": tool_trace,
    }


def _summarize_output(output):
    if isinstance(output, list):
        return {"count": len(output), "preview": output[:2]}
    if isinstance(output, dict):
        return {key: output[key] for key in list(output)[:6]}
    return output
