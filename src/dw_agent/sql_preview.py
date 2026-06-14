from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

FORBIDDEN_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|MERGE|CALL|COPY|ATTACH|DETACH|OVERWRITE|MSCK|REPAIR)\b",
    re.I,
)


def run_duckdb_sql_preview(
    sql: str,
    db_path: str | Path | None = None,
    limit: int = 100,
    key_columns: list[str] | None = None,
) -> dict[str, Any]:
    try:
        preview = preview_duckdb_select(sql, db_path=db_path, limit=limit)
    except Exception as exc:
        return {
            "preview_available": True,
            "passed": False,
            "columns": [],
            "rows": [],
            "row_count": 0,
            "null_rate_summary": {},
            "warnings": [],
            "errors": [f"{type(exc).__name__}: {exc}"],
        }

    warnings = _quality_warnings(preview["columns"], preview["rows"], key_columns or [])
    if preview["row_count"] == 0:
        warnings.append("Preview query returned zero rows.")
    return {
        "preview_available": True,
        "passed": True,
        **preview,
        "warnings": warnings,
        "errors": [],
    }


def preview_duckdb_select(sql: str, db_path: str | Path | None = None, limit: int = 100) -> dict[str, Any]:
    if not _is_select_only(sql):
        raise ValueError("SQL preview only allows a single SELECT/WITH query.")
    try:
        import duckdb
    except ModuleNotFoundError as exc:
        raise RuntimeError("DuckDB SQL preview requires the 'duckdb' package.") from exc

    path = Path(db_path or os.getenv("WAREHOUSE_DUCKDB_PATH") or "./demo/warehouse_demo.duckdb")
    if not path.exists():
        raise FileNotFoundError(f"DuckDB database not found: {path}")

    preview_sql = _with_limit(sql, limit)
    with duckdb.connect(str(path), read_only=True) as conn:
        result = conn.execute(preview_sql)
        columns = [item[0] for item in result.description]
        rows = result.fetchall()
    return {
        "columns": columns,
        "rows": [_serializable_row(columns, row) for row in rows],
        "row_count": len(rows),
        "null_rate_summary": _null_rate_summary(columns, rows),
    }


def _is_select_only(sql: str) -> bool:
    stripped = sql.strip().rstrip(";")
    if not stripped:
        return False
    if ";" in stripped:
        return False
    if FORBIDDEN_SQL.search(stripped):
        return False
    return bool(re.match(r"^\s*(SELECT|WITH)\b", stripped, flags=re.I))


def _with_limit(sql: str, limit: int) -> str:
    stripped = sql.strip().rstrip(";")
    if re.search(r"\bLIMIT\s+\d+\s*$", stripped, flags=re.I):
        return stripped
    return f"{stripped}\nLIMIT {limit}"


def _null_rate_summary(columns: list[str], rows: list[tuple[Any, ...]]) -> dict[str, float]:
    if not rows:
        return {column: 0.0 for column in columns}
    summary = {}
    for index, column in enumerate(columns):
        null_count = sum(1 for row in rows if row[index] is None)
        summary[column] = null_count / len(rows)
    return summary


def _serializable_row(columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
    return {column: _serializable_value(value) for column, value in zip(columns, row, strict=False)}


def _serializable_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _quality_warnings(columns: list[str], rows: list[dict[str, Any]], key_columns: list[str]) -> list[str]:
    warnings = []
    numeric_columns = [
        column
        for column in columns
        if any(token in column.lower() for token in ["amount", "cnt", "count", "num", "rate", "uv", "pv"])
    ]
    for column in numeric_columns:
        if any(_is_negative(row.get(column)) for row in rows):
            warnings.append(f"Column {column} contains negative values.")

    usable_keys = [column for column in key_columns if column in columns]
    if usable_keys:
        seen = set()
        duplicates = 0
        for row in rows:
            key = tuple(row.get(column) for column in usable_keys)
            if key in seen:
                duplicates += 1
            seen.add(key)
        if duplicates:
            warnings.append(f"Preview found {duplicates} duplicate key rows for {', '.join(usable_keys)}.")
    return warnings


def _is_negative(value: Any) -> bool:
    try:
        return value is not None and float(value) < 0
    except (TypeError, ValueError):
        return False
