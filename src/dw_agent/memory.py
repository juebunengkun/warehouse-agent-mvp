from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dw_agent.config import PROJECT_ROOT

DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "sessions.db"


def init_db(db_path: Path = DEFAULT_DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                requirement TEXT NOT NULL,
                parsed_json TEXT NOT NULL,
                reuse_decision_json TEXT NOT NULL,
                sql_validation_json TEXT NOT NULL,
                final_report TEXT NOT NULL
            )
            """)


def save_session(state: dict[str, Any], db_path: Path = DEFAULT_DB_PATH) -> int:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO sessions (
                created_at,
                requirement,
                parsed_json,
                reuse_decision_json,
                sql_validation_json,
                final_report
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(UTC).isoformat(),
                state.get("requirement", ""),
                json.dumps(state.get("parsed", {}), ensure_ascii=False),
                json.dumps(state.get("reuse_decision", {}), ensure_ascii=False),
                json.dumps(state.get("sql_validation", {}), ensure_ascii=False),
                state.get("final_report", ""),
            ),
        )
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return a session id")
        return cursor.lastrowid


def load_relevant_sessions(
    parsed: dict[str, Any], limit: int = 3, db_path: Path = DEFAULT_DB_PATH
) -> list[dict[str, Any]]:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute("""
            SELECT id, created_at, requirement, parsed_json, reuse_decision_json, sql_validation_json
            FROM sessions
            ORDER BY id DESC
            LIMIT 50
            """).fetchall()

    scored = []
    for row in rows:
        item = _row_to_dict(row)
        score = _similarity_score(parsed, item.get("parsed", {}))
        if score > 0:
            item["score"] = score
            scored.append(item)

    scored.sort(key=lambda item: (item["score"], item["id"]), reverse=True)
    return scored[:limit]


def list_recent_sessions(limit: int = 10, db_path: Path = DEFAULT_DB_PATH) -> list[dict[str, Any]]:
    init_db(db_path)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, requirement, parsed_json, reuse_decision_json, sql_validation_json
            FROM sessions
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _row_to_dict(row) -> dict[str, Any]:
    session_id, created_at, requirement, parsed_json, reuse_decision_json, sql_validation_json = row
    return {
        "id": session_id,
        "created_at": created_at,
        "requirement": requirement,
        "parsed": json.loads(parsed_json or "{}"),
        "reuse_decision": json.loads(reuse_decision_json or "{}"),
        "sql_validation": json.loads(sql_validation_json or "{}"),
    }


def _similarity_score(current: dict[str, Any], previous: dict[str, Any]) -> int:
    score = 0
    if current.get("business_theme") and current.get("business_theme") == previous.get("business_theme"):
        score += 3
    score += len(set(current.get("metrics", [])) & set(previous.get("metrics", []))) * 2
    score += len(set(current.get("dimensions", [])) & set(previous.get("dimensions", [])))
    return score
