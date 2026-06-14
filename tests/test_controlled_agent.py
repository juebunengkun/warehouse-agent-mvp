from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _init_duckdb_demo(tmp_path: Path) -> Path:
    script = _project_root() / "demo" / "init_duckdb_demo.py"
    db_path = tmp_path / "warehouse_demo.duckdb"
    env = {**os.environ, "WAREHOUSE_DUCKDB_PATH": str(db_path)}
    subprocess.run([sys.executable, str(script)], cwd=_project_root(), check=True, env=env)
    return db_path


def test_plan_task_generates_agent_plan():
    from dw_agent.nodes.plan_task import plan_task

    result = plan_task(
        {
            "requirement": "Build a category operation daily report.",
            "parsed": {
                "business_theme": "category operation",
                "metrics": ["pay_amount"],
                "dimensions": ["date", "category", "channel"],
                "granularity": "date-category-channel",
                "refresh_cycle": "T+1",
            },
        }
    )

    plan = result["agent_plan"]
    assert plan["goal"]
    assert any(step["step"] == "decide_modeling_strategy" for step in plan["steps"])
    assert {"search_dimensions", "search_facts", "search_summaries"}.issubset(set(plan["tools_needed"]))


def test_clarify_requirement_detects_missing_metric_semantics():
    from dw_agent.nodes.clarify_requirement import clarify_requirement
    from dw_agent.nodes.plan_task import plan_task

    planned = plan_task(
        {
            "requirement": "I want payment amount and new/existing users.",
            "parsed": {
                "business_theme": "payment analysis",
                "metrics": ["pay_amount"],
                "dimensions": ["new/existing user"],
                "granularity": "new/existing user",
                "refresh_cycle": "T+1",
            },
        }
    )
    result = clarify_requirement(planned)
    questions = " ".join(result["clarification"]["questions"])

    assert result["clarification"]["need_clarification"] is True
    assert "payment amount" in questions
    assert "new/existing users" in questions


def test_tool_router_calls_provider(monkeypatch):
    import dw_agent.nodes.tool_router as router

    calls = []

    class FakeProvider:
        def search_dimensions(self, semantic_dimensions):
            calls.append(("search_dimensions", semantic_dimensions))
            return [{"name": "dim_fake_channel_df"}]

        def search_facts(self, metrics, business_process=None):
            calls.append(("search_facts", metrics, business_process))
            return [{"name": "dwd_fake_fact_di"}]

        def search_summaries(self, dimensions, metrics, grain=None, business_process=None):
            calls.append(("search_summaries", dimensions, metrics, grain, business_process))
            return [{"name": "dws_fake_summary_di"}]

        def search_tables(self, **kwargs):
            calls.append(("search_tables", kwargs))
            return [{"name": "ads_fake_report_di"}]

    monkeypatch.setattr(router, "get_metadata_provider", lambda config: FakeProvider())

    result = router.tool_router(
        {
            "parsed": {
                "metrics": ["pay_amount"],
                "dimensions": ["channel"],
                "granularity": "channel",
                "refresh_cycle": "T+1",
            }
        }
    )

    assert {call[0] for call in calls} == {"search_dimensions", "search_facts", "search_summaries", "search_tables"}
    assert not result["tool_errors"]
    assert result["tool_results"]["search_dimensions"][0]["name"] == "dim_fake_channel_df"


def test_sql_preview_rejects_non_select(tmp_path):
    from dw_agent.sql_preview import run_duckdb_sql_preview

    db_path = _init_duckdb_demo(tmp_path)
    preview = run_duckdb_sql_preview("DROP TABLE dim_channel_df", db_path=db_path)

    assert preview["passed"] is False
    assert preview["errors"]


def test_sql_preview_duckdb_select(tmp_path):
    from dw_agent.sql_preview import run_duckdb_sql_preview

    db_path = _init_duckdb_demo(tmp_path)
    preview = run_duckdb_sql_preview("SELECT channel_id, channel_name FROM dim_channel_df", db_path=db_path)

    assert preview["preview_available"] is True
    assert preview["passed"] is True
    assert preview["columns"] == ["channel_id", "channel_name"]
    assert preview["row_count"] >= 1
    assert "null_rate_summary" in preview


def test_verify_outputs_marks_rewrite_on_sql_style_error():
    from dw_agent.nodes.verify_outputs import verify_outputs

    result = verify_outputs(
        {
            "rewrite_count": 0,
            "sql_validation": {"passed": True, "errors": [], "warnings": []},
            "sql_style_review": {
                "passed": False,
                "issues": [{"level": "error", "rule": "NO_SELECT_STAR", "message": "select star is forbidden"}],
            },
            "sql_preview": {"preview_available": False, "passed": False, "warnings": ["skipped"], "errors": []},
            "modeling_strategy": {"fact_tables": []},
        }
    )

    assert result["verification_result"]["need_rewrite"] is True
    assert result["verification_result"]["suggested_next_action"] == "rewrite_sql"


def test_rewrite_count_limited():
    from dw_agent.nodes.rewrite_sql import rewrite_sql
    from dw_agent.nodes.verify_outputs import MAX_REWRITE_COUNT

    state = {
        "rewrite_count": MAX_REWRITE_COUNT,
        "tool_trace": [],
        "sql_validation": {"errors": ["failed"], "warnings": []},
    }
    result = rewrite_sql(state)

    assert result["rewrite_count"] == MAX_REWRITE_COUNT
    assert result["tool_trace"][-1]["output"]["strategy"] == "skipped_rewrite_limit_reached"


def test_graph_contains_agent_nodes(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")

    from dw_agent.graph import run_agent

    requirement = (_project_root() / "examples" / "sales_channel_daily.md").read_text(encoding="utf-8")
    result = run_agent(requirement)

    assert result["agent_plan"]["steps"]
    assert "clarification" in result
    assert result["tool_calls"]
    assert "sql_preview" in result
    assert "verification_result" in result
    assert "Controlled Data Warehouse Agent MVP" in result["final_report"]


def test_information_schema_duckdb_agent_flow(monkeypatch, tmp_path):
    db_path = _init_duckdb_demo(tmp_path)
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")
    monkeypatch.setenv("WAREHOUSE_METADATA_PROVIDER", "information_schema")
    monkeypatch.setenv("WAREHOUSE_DB_TYPE", "duckdb")
    monkeypatch.setenv("WAREHOUSE_DUCKDB_PATH", str(db_path))

    from dw_agent.graph import run_agent

    parsed = {
        "business_theme": "category operation",
        "metrics": ["visit_user_cnt", "exposure_cnt", "click_cnt", "pay_amount", "refund_amount"],
        "dimensions": ["date", "category", "channel", "new/existing user", "member level"],
        "granularity": "stat_date + category_id + channel_id + user_type + member_level",
        "refresh_cycle": "T+1",
        "time_range": "last 30 days",
        "data_layer_target": ["ODS", "DWD", "DWS", "ADS"],
        "sql_dialect": "Hive SQL",
        "assumptions": [],
        "parser_source": "approved_test",
    }
    result = run_agent("category operation daily report", approved_parsed=parsed)

    assert result["sql_validation"]["passed"] is True
    assert result["sql_preview"]["preview_available"] is True
    assert result["sql_preview"]["passed"] is True
    assert result["verification_result"]["checks"]["sql_preview"] == "passed"
