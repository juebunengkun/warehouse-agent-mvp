from __future__ import annotations

from typing import Any

from dw_agent.nodes.common import dimension_columns, metric_columns
from dw_agent.state import AgentState


def generate_ddl(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    strategy = state.get("modeling_strategy", {})
    sections: list[str] = []

    for table in strategy.get("dim_tables", []):
        sections.append(_ddl_for_strategy_table(table, parsed))

    for table in strategy.get("fact_tables", []):
        sections.append(_ddl_for_strategy_table(table, parsed))

    for table in strategy.get("summary_tables", []):
        if table.get("reuse"):
            sections.append(f"-- DWS: reuse existing summary table {table.get('name')}; DDL generation skipped.")
            continue
        sections.append(_ddl_for_strategy_table(table, parsed, fallback_kind="report"))

    for table in strategy.get("application_tables", []):
        sections.append(_ddl_for_strategy_table(table, parsed, fallback_kind="application"))

    ddl = "\n\n".join(section for section in sections if section).strip()
    return {**state, "ddl": ddl + "\n"}


def _ddl_for_strategy_table(table: dict[str, Any], parsed: dict[str, Any], fallback_kind: str = "fact") -> str:
    table_name = str(table.get("name") or "generated_table")
    partition_key = str(table.get("partition_key") or "dt")
    fields = _fields_for_table(table, parsed, fallback_kind)
    columns = [
        (field["name"], field.get("type", "STRING"), field.get("comment", ""))
        for field in fields
        if field.get("name") and field.get("name") != partition_key
    ]
    comment = _escape_comment(
        table.get("description") or f"{table.get('layer', '')} {table.get('table_type', '')} table"
    )
    return f"""CREATE TABLE IF NOT EXISTS {table_name} (
{_format_columns(columns)}
)
COMMENT '{comment}'
PARTITIONED BY ({partition_key} STRING COMMENT 'partition date')
STORED AS ORC;"""


def _fields_for_table(table: dict[str, Any], parsed: dict[str, Any], fallback_kind: str) -> list[dict[str, Any]]:
    metadata_fields = [field for field in table.get("fields", []) if field.get("name")]
    if metadata_fields:
        return metadata_fields

    if fallback_kind in {"report", "application"}:
        fields = _report_fields(parsed)
        if fallback_kind == "application":
            fields = [*fields, {"name": "update_time", "type": "STRING", "comment": "data update time"}]
        return fields

    fields = _report_fields(parsed)
    if not any(field["name"] == "event_id" for field in fields):
        fields.insert(0, {"name": "event_id", "type": "STRING", "comment": "source event id"})
    return fields


def _report_fields(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [*dimension_columns(parsed.get("dimensions", [])), *metric_columns(parsed.get("metrics", []))]
    fields = []
    seen: set[str] = set()
    for _, field_name, sql_type, comment in rows:
        if field_name in seen:
            continue
        seen.add(field_name)
        fields.append({"name": field_name, "type": sql_type, "comment": comment})
    fields.append({"name": "dt", "type": "STRING", "comment": "partition date"})
    return fields


def _format_columns(columns: list[tuple[str, str, str]]) -> str:
    lines = []
    for index, (field, sql_type, comment) in enumerate(columns):
        comma = "," if index < len(columns) - 1 else ""
        lines.append(f"  {field} {sql_type} COMMENT '{_escape_comment(comment)}'{comma}")
    return "\n".join(lines) if lines else "  placeholder STRING COMMENT 'placeholder'"


def _escape_comment(value: Any) -> str:
    return str(value).replace("'", "''")
