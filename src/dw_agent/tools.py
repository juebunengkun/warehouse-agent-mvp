from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from dw_agent.nodes.common import (
    DIMENSION_COLUMNS,
    METRIC_COLUMNS,
    METRIC_SQL,
    dimension_columns,
    group_fields,
    metric_columns,
)
from dw_agent.rag import KnowledgeBase


def knowledge_search_tool(kb_path: str, query: str, top_k: int = 4) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results = KnowledgeBase(kb_path).search(query, top_k=top_k)
    return results, {
        "tool": "knowledge_search",
        "input": {"query": query, "top_k": top_k},
        "output": {"hit_count": len(results), "top_sources": [item["source"] for item in results]},
    }


def metric_lookup_tool(metrics: list[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    results = []
    for metric in metrics:
        field, sql_type, comment = METRIC_COLUMNS.get(metric, ("", "", "未命中模拟指标库"))
        results.append(
            {
                "metric": metric,
                "matched": metric in METRIC_COLUMNS,
                "field": field,
                "type": sql_type,
                "comment": comment,
                "expression": METRIC_SQL.get(metric, ""),
            }
        )
    return results, {
        "tool": "metric_lookup",
        "input": {"metrics": metrics},
        "output": {"matched": [item["metric"] for item in results if item["matched"]]},
    }


def metadata_lookup_tool(kb_path: str, parsed: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = Path(kb_path) / "table_metadata.json"
    if not path.exists():
        return [], {"tool": "metadata_lookup", "input": {}, "output": {"error": "table_metadata.json not found"}}

    data = json.loads(path.read_text(encoding="utf-8"))
    keywords = set(parsed.get("metrics", [])) | set(parsed.get("dimensions", []))
    topic = str(parsed.get("business_theme", "")).replace("主题", "")
    if topic:
        keywords.add(topic)

    candidates = []
    for table in data.get("tables", []):
        payload = json.dumps(table, ensure_ascii=False)
        score = sum(1 for keyword in keywords if keyword and keyword in payload)
        if score > 0:
            candidates.append(
                {
                    "name": table.get("name"),
                    "layer": table.get("layer"),
                    "description": table.get("description"),
                    "score": score,
                }
            )
    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:6], {
        "tool": "metadata_lookup",
        "input": {"keywords": sorted(keywords)},
        "output": {"candidate_count": len(candidates[:6]), "tables": [item["name"] for item in candidates[:6]]},
    }


def sql_validation_tool(ddl: str, etl_sql: str, parsed: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []

    if "PARTITIONED BY (dt STRING" not in ddl:
        errors.append("DDL 未统一声明 dt 分区。")

    insert_count = len(re.findall(r"INSERT\s+OVERWRITE\s+TABLE", etl_sql, flags=re.IGNORECASE))
    if insert_count < 3:
        errors.append("ETL SQL 应至少包含 DWD、DWS、ADS 三段 INSERT OVERWRITE。")

    if "WHERE dt = '${bizdate}'" not in etl_sql and "WHERE dt='${bizdate}'" not in etl_sql:
        errors.append("ETL SQL 未显式过滤上游 dt='${bizdate}'。")

    group_by = group_fields(parsed)
    group_by_clause = "GROUP BY " + ", ".join(group_by)
    if group_by and group_by_clause not in etl_sql:
        errors.append(f"DWS 聚合 SQL 的 GROUP BY 与解析粒度不一致，应为：{', '.join(group_by)}。")

    for _, field, _, _ in dimension_columns(parsed.get("dimensions", [])):
        if field not in ddl:
            errors.append(f"DDL 缺少维度字段：{field}。")

    for _, field, _, _ in metric_columns(parsed.get("metrics", [])):
        if field not in ddl:
            errors.append(f"DDL 缺少指标字段：{field}。")
        if f"AS {field}" not in etl_sql and field not in ["update_time"]:
            warnings.append(f"ETL SQL 未发现指标别名：{field}，请确认是否为派生或下游透传字段。")

    unknown_metrics = [metric for metric in parsed.get("metrics", []) if metric not in METRIC_COLUMNS]
    if unknown_metrics:
        warnings.append(f"存在未命中指标口径库的指标：{', '.join(unknown_metrics)}。")

    unknown_dimensions = [dimension for dimension in parsed.get("dimensions", []) if dimension not in DIMENSION_COLUMNS]
    if unknown_dimensions:
        warnings.append(f"存在未命中维度模板的维度：{', '.join(unknown_dimensions)}。")

    validation = {
        "passed": not errors,
        "errors": errors,
        "warnings": warnings,
        "checks": [
            "dt_partition",
            "insert_count",
            "upstream_dt_filter",
            "group_by_grain",
            "ddl_dimension_fields",
            "ddl_metric_fields",
            "known_metric_definitions",
        ],
    }
    return validation, {
        "tool": "sql_validation",
        "input": {"dimensions": parsed.get("dimensions", []), "metrics": parsed.get("metrics", [])},
        "output": {"passed": validation["passed"], "error_count": len(errors), "warning_count": len(warnings)},
    }
