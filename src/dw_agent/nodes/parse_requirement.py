from __future__ import annotations

import json
import re

from dw_agent.llm import get_chat_model
from dw_agent.nodes.common import METRIC_COLUMNS
from dw_agent.state import AgentState


KNOWN_DIMENSIONS = ["日期", "地区", "渠道", "商品", "用户"]


def parse_requirement(state: AgentState) -> AgentState:
    if state.get("human_confirmed") and state.get("parsed"):
        return state

    requirement = state["requirement"]
    parsed = _parse_with_rules(requirement)
    parsed = _parse_with_llm(requirement, parsed)
    return {**state, "parsed": parsed}


def _parse_with_rules(requirement: str) -> dict:
    metrics = _extract_metrics(requirement)
    dimensions = _extract_dimensions(requirement)
    refresh_cycle = _extract_refresh_cycle(requirement)
    time_range = _extract_time_range(requirement)
    business_theme = _extract_theme(requirement)
    granularity = _build_granularity(dimensions)

    parsed = {
        "business_theme": business_theme,
        "metrics": metrics,
        "dimensions": dimensions,
        "granularity": granularity,
        "refresh_cycle": refresh_cycle,
        "time_range": time_range,
        "data_layer_target": ["ODS", "DWD", "DWS", "ADS"],
        "sql_dialect": "Hive SQL",
        "assumptions": _assumptions(metrics, dimensions),
        "parser_source": "rules",
    }
    return parsed


def _parse_with_llm(requirement: str, fallback: dict) -> dict:
    model = get_chat_model()
    if model is None:
        return fallback

    prompt = f"""你是资深数据仓库需求分析助手。
请把用户的报表需求解析成严格 JSON，不要输出 Markdown。

必须返回这些字段：
- business_theme: 字符串，例如 "销售主题"
- metrics: 字符串数组
- dimensions: 字符串数组，只保留真正的统计维度，不要把“支付用户数”里的“用户”误判成维度
- granularity: 字符串，例如 "日期-地区-渠道"
- refresh_cycle: 字符串
- time_range: 字符串
- assumptions: 字符串数组

已知指标口径可选：{", ".join(METRIC_COLUMNS.keys())}
常见维度可选：{", ".join(KNOWN_DIMENSIONS)}

用户需求：
{requirement}

规则解析结果，可作为兜底参考：
{json.dumps(fallback, ensure_ascii=False)}
"""
    try:
        response = model.invoke(prompt)
        content = str(getattr(response, "content", response))
        data = _extract_json(content)
        parsed = {
            **fallback,
            "business_theme": _clean_text(data.get("business_theme"), fallback["business_theme"]),
            "metrics": _clean_list(data.get("metrics"), fallback["metrics"]),
            "dimensions": _clean_list(data.get("dimensions"), fallback["dimensions"]),
            "refresh_cycle": _clean_text(data.get("refresh_cycle"), fallback["refresh_cycle"]),
            "time_range": _clean_text(data.get("time_range"), fallback["time_range"]),
            "parser_source": "llm",
        }
        parsed["granularity"] = _clean_text(data.get("granularity"), _build_granularity(parsed["dimensions"]))
        parsed["assumptions"] = _clean_list(data.get("assumptions"), fallback["assumptions"])
        parsed["data_layer_target"] = ["ODS", "DWD", "DWS", "ADS"]
        parsed["sql_dialect"] = "Hive SQL"
        return parsed
    except Exception as exc:
        fallback["parser_source"] = "rules_fallback_after_llm_error"
        fallback["assumptions"] = [
            *fallback.get("assumptions", []),
            f"LLM 调用失败，已回退到规则解析：{type(exc).__name__}。",
        ]
        return fallback


def _extract_json(content: str) -> dict:
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM response does not contain a JSON object")
    return json.loads(content[start : end + 1])


def _clean_list(value, fallback: list[str]) -> list[str]:
    if not isinstance(value, list):
        return fallback
    cleaned = [str(item).strip() for item in value if str(item).strip()]
    return cleaned or fallback


def _clean_text(value, fallback: str) -> str:
    if value is None:
        return fallback
    cleaned = str(value).strip()
    return cleaned or fallback


def _extract_metrics(text: str) -> list[str]:
    found = [metric for metric in METRIC_COLUMNS if metric in text]
    if found:
        return found

    match = re.search(r"指标[为是包括:：]?(.*?)(?:维度|粒度|刷新|周期|。|$)", text)
    if not match:
        return ["销售额", "订单数"]

    raw = re.split(r"[、,，和及\s]+", match.group(1))
    return [item.strip() for item in raw if item.strip()]


def _extract_dimensions(text: str) -> list[str]:
    found: list[str] = []

    for segment in _dimension_segments(text):
        if "天" in segment or "日" in segment or "日期" in segment:
            found.append("日期")
        for dimension in KNOWN_DIMENSIONS:
            if dimension in segment:
                found.append(dimension)

    if not found:
        if "日报" in text or "每天" in text or "每日" in text:
            found.append("日期")
        for dimension in ["地区", "渠道", "商品"]:
            if dimension in text:
                found.append(dimension)
        if re.search(r"(按|按照|以).{0,8}用户|用户维度|用户粒度", text):
            found.append("用户")

    if ("天" in text or "日报" in text or "每天" in text or "每日" in text) and "日期" not in found:
        found.insert(0, "日期")

    ordered: list[str] = []
    for dimension in found:
        if dimension not in ordered:
            ordered.append(dimension)
    return ordered or ["日期"]


def _dimension_segments(text: str) -> list[str]:
    segments = []
    patterns = [
        r"(?:按|按照|以)(.*?)(?:统计|分析|查看|计算|输出|生成|展示)",
        r"维度[为是包括:：]?(.*?)(?:指标|粒度|刷新|周期|统计|。|$)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            segments.append(match.group(1))
    return segments


def _extract_refresh_cycle(text: str) -> str:
    if re.search(r"T\s*\+\s*1", text, re.IGNORECASE):
        return "T+1 日刷新"
    if "实时" in text:
        return "实时/准实时"
    if "每小时" in text or "小时" in text:
        return "小时级刷新"
    if "每月" in text or "月报" in text:
        return "月刷新"
    if "每周" in text or "周报" in text:
        return "周刷新"
    if "日报" in text or "每天" in text or "每日" in text:
        return "T+1 日刷新"
    return "待确认"


def _extract_time_range(text: str) -> str:
    match = re.search(r"近\s*(\d+)\s*(天|日|周|月)", text)
    if match:
        return f"近 {match.group(1)} {match.group(2)}"
    return "待确认"


def _extract_theme(text: str) -> str:
    for theme in ["销售", "交易", "订单", "用户", "流量", "商品", "库存", "营销", "财务"]:
        if theme in text:
            return f"{theme}主题"
    return "通用报表主题"


def _build_granularity(dimensions: list[str]) -> str:
    return "-".join(dimensions) if dimensions else "待确认"


def _assumptions(metrics: list[str], dimensions: list[str]) -> list[str]:
    assumptions = []
    if "日期" not in dimensions:
        assumptions.append("未显式提供日期维度，默认按分区日期产出。")
    if any(metric not in METRIC_COLUMNS for metric in metrics):
        assumptions.append("部分指标未在模拟指标库中命中，需要人工补充口径。")
    assumptions.append("MVP 默认使用 Hive 分区表，分区字段为 dt。")
    return assumptions
