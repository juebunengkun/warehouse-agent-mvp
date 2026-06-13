from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

FORBIDDEN_SQL = re.compile(r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|MERGE|CALL|COPY|ATTACH|DETACH)\b", re.I)


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
        "rows": [dict(zip(columns, row, strict=False)) for row in rows],
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
