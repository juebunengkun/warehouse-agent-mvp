from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dw_agent.sql_preview import run_duckdb_sql_preview
from dw_agent.state import AgentState


def sql_preview(state: AgentState) -> AgentState:
    preview = _build_preview(state)
    trace = {
        "tool": "sql_preview",
        "input": {
            "provider": os.getenv("WAREHOUSE_METADATA_PROVIDER", "local_json"),
            "db_type": os.getenv("WAREHOUSE_DB_TYPE", ""),
        },
        "output": {
            "preview_available": preview.get("preview_available"),
            "passed": preview.get("passed"),
            "row_count": preview.get("row_count"),
            "error_count": len(preview.get("errors", [])),
            "reason": preview.get("reason"),
        },
    }
    return {**state, "sql_preview": preview, "tool_trace": [*state.get("tool_trace", []), trace]}


def _build_preview(state: AgentState) -> dict[str, Any]:
    provider = os.getenv("WAREHOUSE_METADATA_PROVIDER", "local_json").lower()
    db_type = os.getenv("WAREHOUSE_DB_TYPE", "duckdb").lower()
    if provider not in {"information_schema", "infoschema", "database"} or db_type != "duckdb":
        return _skipped("SQL preview only supports local DuckDB information_schema demo in MVP stage.")

    db_path = Path(os.getenv("WAREHOUSE_DUCKDB_PATH") or "./demo/warehouse_demo.duckdb")
    if not db_path.exists():
        return _skipped(f"DuckDB demo database not found: {db_path}.")

    table = _preview_table(state)
    if not table:
        return _skipped("No provider-backed table is available for DuckDB preview.")

    key_columns = _key_columns(table)
    sql = f"SELECT * FROM {table['name']}"
    partition_key = table.get("partition_key")
    if partition_key and partition_key in {field.get("name") for field in table.get("fields", [])}:
        sql += f" WHERE {partition_key} = (SELECT MAX({partition_key}) FROM {table['name']})"

    return run_duckdb_sql_preview(sql, db_path=db_path, limit=100, key_columns=key_columns)


def _preview_table(state: AgentState) -> dict[str, Any] | None:
    strategy = state.get("modeling_strategy", {})
    for group in ["application_tables", "summary_tables", "fact_tables", "dim_tables"]:
        for table in strategy.get(group, []):
            name = str(table.get("name") or "")
            if name and not name.startswith(("ads_generated_", "dws_generated_", "dwd_generated_", "dim_generated_")):
                return table
    return None


def _key_columns(table: dict[str, Any]) -> list[str]:
    primary_keys = [str(key) for key in table.get("primary_keys", []) if key]
    if primary_keys:
        return primary_keys
    grain = str(table.get("grain") or "")
    return [item.strip() for item in grain.replace("+", ",").split(",") if item.strip()]


def _skipped(reason: str) -> dict[str, Any]:
    return {
        "preview_available": False,
        "passed": False,
        "reason": reason,
        "columns": [],
        "rows": [],
        "row_count": 0,
        "null_rate_summary": {},
        "warnings": [reason],
        "errors": [],
    }
