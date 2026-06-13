from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    requirement: str
    knowledge_base_path: str
    session_id: int
    auto_confirm: bool
    human_confirmed: bool
    parsed: dict[str, Any]
    agent_decision: str
    clarification_questions: list[str]
    tool_trace: list[dict[str, Any]]
    metric_context: list[dict[str, Any]]
    metadata_candidates: list[dict[str, Any]]
    memory_context: list[dict[str, Any]]
    reuse_decision: dict[str, Any]
    retrievals: dict[str, list[dict[str, Any]]]
    modeling_plan: str
    ddl: str
    etl_sql: str
    validation_attempts: int
    sql_validation: dict[str, Any]
    dqc_rules: str
    review: str
    final_report: str
