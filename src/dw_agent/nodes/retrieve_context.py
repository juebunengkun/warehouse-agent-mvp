from __future__ import annotations

from dw_agent.state import AgentState
from dw_agent.tools import knowledge_search_tool, metadata_lookup_tool, metric_lookup_tool


def retrieve_context(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    kb_path = state["knowledge_base_path"]
    tool_trace = [*state.get("tool_trace", [])]

    metrics = " ".join(parsed.get("metrics", []))
    dimensions = " ".join(parsed.get("dimensions", []))
    theme = parsed.get("business_theme", "")

    standards, trace = knowledge_search_tool(kb_path, f"ODS DWD DWS ADS 命名 分区 粒度 {theme}", top_k=4)
    tool_trace.append(trace)
    metric_docs, trace = knowledge_search_tool(kb_path, f"{metrics} 指标 口径 计算 依赖字段", top_k=4)
    tool_trace.append(trace)
    table_docs, trace = knowledge_search_tool(kb_path, f"{theme} {metrics} {dimensions} 表结构 字段 明细 汇总", top_k=5)
    tool_trace.append(trace)
    dqc_docs, trace = knowledge_search_tool(kb_path, f"{metrics} {dimensions} DQC 非空 唯一 波动 分区", top_k=4)
    tool_trace.append(trace)

    metric_context, trace = metric_lookup_tool(parsed.get("metrics", []))
    tool_trace.append(trace)
    metadata_candidates, trace = metadata_lookup_tool(kb_path, parsed)
    tool_trace.append(trace)

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
