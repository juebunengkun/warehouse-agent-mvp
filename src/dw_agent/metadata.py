from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dw_agent.config import DEFAULT_KB_PATH


def load_table_metadata(kb_path: str | Path | None = None) -> list[dict[str, Any]]:
    path = Path(kb_path) if kb_path else DEFAULT_KB_PATH
    data = json.loads((path / "table_metadata.json").read_text(encoding="utf-8"))
    return list(data.get("tables", []))


def get_table_metadata(table_name: str, kb_path: str | Path | None = None) -> dict[str, Any] | None:
    for table in load_table_metadata(kb_path):
        if table.get("name") == table_name:
            return table
    return None


def table_suffix(table_name: str) -> str:
    if table_name.endswith("_di"):
        return "_di"
    if table_name.endswith("_df"):
        return "_df"
    return ""


def field_names(table: dict[str, Any]) -> set[str]:
    return {str(field.get("name")) for field in table.get("fields", []) if field.get("name")}


def grain_fields(table: dict[str, Any]) -> set[str]:
    grain = str(table.get("grain", ""))
    if not grain:
        return set()
    return {item.strip() for item in grain.split("+") if item.strip()}


def find_tables_by_names(table_names: list[str], kb_path: str | Path | None = None) -> list[dict[str, Any]]:
    lookup = {table.get("name"): table for table in load_table_metadata(kb_path)}
    return [lookup[name] for name in table_names if name in lookup]
