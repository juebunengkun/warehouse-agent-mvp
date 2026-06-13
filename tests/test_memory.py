from __future__ import annotations


def test_sqlite_memory_saves_and_loads_relevant_sessions(monkeypatch, tmp_path):
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")

    from dw_agent.memory import load_relevant_sessions, save_session

    db_path = tmp_path / "sessions.db"
    state = {
        "requirement": "销售日报",
        "parsed": {
            "business_theme": "销售主题",
            "metrics": ["销售额", "订单数"],
            "dimensions": ["日期", "地区"],
        },
        "reuse_decision": {"decision": "reuse_existing_dws"},
        "sql_validation": {"passed": True},
        "final_report": "ok",
    }

    session_id = save_session(state, db_path=db_path)
    matches = load_relevant_sessions(state["parsed"], db_path=db_path)

    assert session_id == 1
    assert matches[0]["id"] == session_id
    assert matches[0]["score"] > 0
