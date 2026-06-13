from __future__ import annotations

import json
import os

import streamlit as st
from dotenv import load_dotenv

from dw_agent.graph import run_agent
from dw_agent.llm import llm_enabled

load_dotenv()

DEFAULT_REQUIREMENT = """做一个销售经营日报，按天、地区、渠道统计销售额、订单数、支付用户数和客单价。
要求 T+1 每天早上刷新，可以查看近 30 天数据。"""


def split_items(text: str) -> list[str]:
    return [item.strip() for item in text.replace(",", "、").replace("，", "、").split("、") if item.strip()]


def join_items(items: list[str]) -> str:
    return "、".join(items or [])


def render_llm_diagnostics(diagnostics: dict) -> None:
    if not diagnostics:
        return
    status = diagnostics.get("status")
    model = diagnostics.get("model", "unknown")
    if status == "success":
        st.success(f"LLM 解析成功：{model}")
    elif status == "failed":
        st.warning("LLM 已尝试调用但失败，Agent 已回退到规则解析：" f"{diagnostics.get('error_type', 'unknown error')}")
    elif diagnostics.get("enabled") and diagnostics.get("has_api_key"):
        st.info(f"LLM 已配置：{model}，当前结果未使用 LLM。")
    else:
        st.info("LLM 未启用，当前使用规则解析。")


def render_agent_result(result: dict) -> None:
    parsed_col, rag_col = st.columns([1, 1])

    with parsed_col:
        st.subheader("结构化需求")
        render_llm_diagnostics(result.get("llm_diagnostics", {}))
        st.json(result.get("parsed", {}), expanded=True)

    with rag_col:
        st.subheader("RAG 命中文档")
        retrievals = result.get("retrievals", {})
        for group, docs in retrievals.items():
            with st.expander(group, expanded=False):
                for doc in docs:
                    st.markdown(f"**{doc['title']}** · `{doc['source']}` · score={doc['score']}")
                    st.write(doc["excerpt"])

    tabs = st.tabs(
        [
            "建模方案",
            "建模策略",
            "表复用",
            "DDL",
            "ETL SQL",
            "DQC",
            "SQL 自检",
            "SQL 风格",
            "记忆",
            "Agent 轨迹",
            "审阅",
            "完整报告",
        ]
    )

    with tabs[0]:
        st.markdown(result.get("modeling_plan", ""))

    with tabs[1]:
        st.json(result.get("modeling_strategy", {}), expanded=True)

    with tabs[2]:
        st.json(result.get("reuse_decision", {}), expanded=True)

    with tabs[3]:
        st.code(result.get("ddl", ""), language="sql")

    with tabs[4]:
        st.code(result.get("etl_sql", ""), language="sql")

    with tabs[5]:
        st.markdown(result.get("dqc_rules", ""))

    with tabs[6]:
        validation = result.get("sql_validation", {})
        if validation.get("passed"):
            st.success("SQL 自检通过")
        else:
            st.error("SQL 自检存在问题")
        st.json(validation, expanded=True)

    with tabs[7]:
        style_review = result.get("sql_style_review", {})
        if style_review.get("passed"):
            st.success("SQL 风格审查通过")
        else:
            st.warning("SQL 风格审查存在问题")
        st.json(style_review, expanded=True)

    with tabs[8]:
        if result.get("session_id"):
            st.success(f"当前结果已保存为 session #{result['session_id']}")
        memory_context = result.get("memory_context", [])
        if memory_context:
            st.json(memory_context, expanded=False)
        else:
            st.info("暂无相关历史会话。")

    with tabs[9]:
        trace = result.get("tool_trace", [])
        if not trace:
            st.info("暂无工具调用轨迹。")
        for index, item in enumerate(trace, start=1):
            with st.expander(f"{index}. {item.get('tool')}", expanded=False):
                st.json(item, expanded=True)

    with tabs[10]:
        st.markdown(result.get("review", ""))

    with tabs[11]:
        st.download_button(
            "下载 Markdown 报告",
            data=result.get("final_report", ""),
            file_name="warehouse_modeling_report.md",
            mime="text/markdown",
        )
        st.markdown(result.get("final_report", ""))

    with st.expander("原始状态 JSON"):
        st.code(json.dumps(result, ensure_ascii=False, indent=2), language="json")


st.set_page_config(page_title="数仓建模 Agent MVP", layout="wide")

st.title("数仓建模 Agent MVP")
st.caption("输入报表需求，Agent 会先解析并等待确认，再调用工具生成 ODS/DWD/DWS/ADS 方案、SQL 和 DQC。")

with st.sidebar:
    st.subheader("运行说明")
    st.write("当前知识库来自 `knowledge_base/` 下的模拟规范、指标和表结构。")
    if llm_enabled() and os.getenv("OPENAI_API_KEY"):
        st.success(f"LLM 已启用：{os.getenv('OPENAI_MODEL', 'gpt-4.1-mini')}")
    else:
        st.warning("LLM 未启用：请在 `.env` 填写 `OPENAI_API_KEY`。")
    st.write("没有 API Key 时会使用规则模板；配置 `.env` 后需求解析会优先调用 LLM。")
    st.write("当前流程：需求解析 -> 人工确认 -> MCP 工具检索 -> 表复用判断 -> SQLGlot 自检 -> SQLite 记忆。")

requirement = st.text_area("报表需求", value=DEFAULT_REQUIREMENT, height=160)

parse_col, direct_col = st.columns([1, 1])
with parse_col:
    parse_clicked = st.button("1. 解析需求", type="primary")
with direct_col:
    direct_clicked = st.button("跳过确认，直接生成")

if parse_clicked:
    with st.spinner("Agent 正在解析需求并判断是否需要确认..."):
        draft = run_agent(requirement, require_confirmation=True)
    st.session_state["draft_state"] = draft
    st.session_state.pop("agent_result", None)

if direct_clicked:
    with st.spinner("Agent 正在直接生成完整方案..."):
        result = run_agent(requirement)
    st.session_state["agent_result"] = result
    st.session_state.pop("draft_state", None)

draft_state = st.session_state.get("draft_state")
result = st.session_state.get("agent_result")

if st.query_params.get("demo") == "1" and not result and not draft_state:
    with st.spinner("Agent 正在生成 demo 报告..."):
        result = run_agent(requirement)
    st.session_state["agent_result"] = result
    st.rerun()

if draft_state and not result:
    parsed = draft_state.get("parsed", {})
    st.subheader("待确认的结构化需求")
    st.info("Agent 已经完成需求解析。请确认或修改下面字段，再继续生成方案。")

    questions = draft_state.get("clarification_questions", [])
    if questions:
        with st.expander("Agent 的确认问题", expanded=True):
            for question in questions:
                st.write(f"- {question}")

    with st.form("confirm_requirement_form"):
        business_theme = st.text_input("业务主题", value=parsed.get("business_theme", ""))
        metrics_text = st.text_input("指标（用、分隔）", value=join_items(parsed.get("metrics", [])))
        dimensions_text = st.text_input("维度（用、分隔）", value=join_items(parsed.get("dimensions", [])))
        refresh_cycle = st.text_input("刷新周期", value=parsed.get("refresh_cycle", ""))
        time_range = st.text_input("时间范围", value=parsed.get("time_range", ""))
        assumptions_text = st.text_area(
            "假设/补充说明（一行一个）", value="\n".join(parsed.get("assumptions", [])), height=120
        )
        confirmed = st.form_submit_button("2. 确认并生成方案", type="primary")

    if confirmed:
        confirmed_parsed = {
            **parsed,
            "business_theme": business_theme,
            "metrics": split_items(metrics_text),
            "dimensions": split_items(dimensions_text),
            "granularity": "-".join(split_items(dimensions_text)) or "待确认",
            "refresh_cycle": refresh_cycle,
            "time_range": time_range,
            "assumptions": [line.strip() for line in assumptions_text.splitlines() if line.strip()],
            "data_layer_target": ["ODS", "DWD", "DWS", "ADS"],
            "sql_dialect": "Hive SQL",
            "parser_source": f"{parsed.get('parser_source', 'unknown')}_human_confirmed",
        }
        with st.spinner("Agent 正在检索知识库、生成 SQL 并自检..."):
            result = run_agent(requirement, approved_parsed=confirmed_parsed)
        st.session_state["agent_result"] = result
        st.session_state.pop("draft_state", None)
        st.rerun()

if result:
    render_agent_result(result)
elif not draft_state:
    st.info("填写一个报表需求，然后点击“1. 解析需求”。")
