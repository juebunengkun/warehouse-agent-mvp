from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import sqlglot
from sqlglot import exp

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
    structural_checks = _sqlglot_structural_checks(ddl, etl_sql, parsed)
    errors.extend(structural_checks["errors"])
    warnings.extend(structural_checks["warnings"])

    if "PARTITIONED BY (dt STRING" not in ddl:
        errors.append("DDL 未统一声明 dt 分区。")

    reuse_existing_dws = parsed.get("reuse_decision", {}).get("decision") == "reuse_existing_dws"

    insert_count = len(re.findall(r"INSERT\s+OVERWRITE\s+TABLE", etl_sql, flags=re.IGNORECASE))
    min_insert_count = 2 if reuse_existing_dws else 3
    if insert_count < min_insert_count:
        expected = (
            "DWD、ADS 两段 INSERT OVERWRITE（复用 DWS 模式）"
            if reuse_existing_dws
            else "DWD、DWS、ADS 三段 INSERT OVERWRITE"
        )
        errors.append(f"ETL SQL 应至少包含 {expected}。")

    if "WHERE dt = '${bizdate}'" not in etl_sql and "WHERE dt='${bizdate}'" not in etl_sql:
        errors.append("ETL SQL 未显式过滤上游 dt='${bizdate}'。")

    group_by = group_fields(parsed)
    group_by_clause = "GROUP BY " + ", ".join(group_by)
    if group_by and group_by_clause not in etl_sql and not reuse_existing_dws:
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
            "sqlglot_parse",
            "sqlglot_group_by_alignment",
        ],
        "sqlglot": structural_checks["summary"],
    }
    return validation, {
        "tool": "sql_validation",
        "input": {"dimensions": parsed.get("dimensions", []), "metrics": parsed.get("metrics", [])},
        "output": {"passed": validation["passed"], "error_count": len(errors), "warning_count": len(warnings)},
    }


def _sqlglot_structural_checks(ddl: str, etl_sql: str, parsed: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, Any] = {
        "ddl_statement_count": 0,
        "etl_statement_count": 0,
        "dws_group_by_fields": [],
        "dws_non_aggregate_fields": [],
    }

    try:
        ddl_statements = sqlglot.parse(ddl, read="hive")
        summary["ddl_statement_count"] = len([statement for statement in ddl_statements if statement])
    except Exception as exc:
        errors.append(f"sqlglot 无法解析 DDL：{type(exc).__name__}: {exc}")

    try:
        etl_statements = [statement for statement in sqlglot.parse(etl_sql, read="hive") if statement]
        summary["etl_statement_count"] = len(etl_statements)
    except Exception as exc:
        errors.append(f"sqlglot 无法解析 ETL SQL：{type(exc).__name__}: {exc}")
        return {"errors": errors, "warnings": warnings, "summary": summary}

    reuse_existing_dws = parsed.get("reuse_decision", {}).get("decision") == "reuse_existing_dws"
    dws_insert = _find_insert_for_table(etl_statements, "dws_")
    if dws_insert is None:
        if reuse_existing_dws:
            summary["dws_reuse_mode"] = True
        else:
            warnings.append("sqlglot 未定位到 DWS INSERT 语句，无法做 DWS GROUP BY 结构检查。")
        return {"errors": errors, "warnings": warnings, "summary": summary}

    select = dws_insert.expression if isinstance(dws_insert, exp.Insert) else dws_insert.find(exp.Select)
    if not isinstance(select, exp.Select):
        warnings.append("sqlglot 未在 DWS INSERT 中定位到 SELECT。")
        return {"errors": errors, "warnings": warnings, "summary": summary}

    group = select.args.get("group")
    group_fields = [expression.sql(dialect="hive") for expression in group.expressions] if group else []
    non_aggregate_fields = []
    for expression in select.expressions:
        if expression.find(exp.AggFunc):
            continue
        column = expression.this if isinstance(expression, exp.Alias) else expression
        non_aggregate_fields.append(column.sql(dialect="hive"))

    summary["dws_group_by_fields"] = group_fields
    summary["dws_non_aggregate_fields"] = non_aggregate_fields

    missing_from_group = sorted(set(non_aggregate_fields) - set(group_fields))
    if missing_from_group:
        errors.append(f"DWS SELECT 非聚合字段未全部出现在 GROUP BY 中：{', '.join(missing_from_group)}。")

    expected_group_fields = set(globals()["group_fields"](parsed))
    if expected_group_fields and expected_group_fields != set(group_fields):
        errors.append(
            "sqlglot 检查发现 DWS GROUP BY 与解析粒度不一致："
            f"期望 {', '.join(sorted(expected_group_fields))}，实际 {', '.join(sorted(group_fields))}。"
        )

    return {"errors": errors, "warnings": warnings, "summary": summary}


def _find_insert_for_table(statements: list[Any], table_prefix: str) -> exp.Insert | None:
    for statement in statements:
        if not isinstance(statement, exp.Insert):
            continue
        table = statement.this
        table_sql = table.sql(dialect="hive") if table is not None else ""
        if table_prefix in table_sql:
            return statement
    return None
