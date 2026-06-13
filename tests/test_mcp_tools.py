from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path


def test_mcp_health_and_metadata_tools():
    from mcp_server.tools.warehouse import get_table_schema, health_check, list_tables

    health = health_check()
    assert health["status"] == "ok"
    assert health["table_count"] >= 1

    dws_tables = list_tables("DWS")
    assert any(table["name"] == "dws_sales_day_summary_di" for table in dws_tables)

    schema = get_table_schema("dws_sales_day_summary_di")
    assert schema["matched"] is True
    assert any(field["name"] == "sales_amount" for field in schema["fields"])


def test_mcp_metric_and_search_tools():
    from mcp_server.tools.warehouse import get_metric_definition, search_warehouse_docs

    metric = get_metric_definition("销售额")
    assert metric["matched"] is True
    assert metric["field"] == "sales_amount"
    assert "SUM" in metric["expression"]

    hits = search_warehouse_docs("销售额 订单数 DWS 粒度", top_k=3)
    assert hits
    assert all("title" in hit and "source" in hit for hit in hits)


def test_mcp_validate_sql_tool(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")

    from dw_agent.graph import run_agent
    from mcp_server.tools.warehouse import validate_sql

    result = run_agent("做一个销售日报，按天、地区、渠道统计销售额和订单数，T+1 刷新。")
    validation = validate_sql(result["ddl"], result["etl_sql"], result["parsed"])

    assert validation["passed"] is True


def test_mcp_server_stdio_health_tool(monkeypatch):
    monkeypatch.setenv("WAREHOUSE_AGENT_USE_LLM", "false")

    async def run_check():
        from mcp.client.session import ClientSession
        from mcp.client.stdio import StdioServerParameters, stdio_client

        project_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        env["PYTHONPATH"] = f"{project_root / 'src'};{project_root}"
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_server.server"],
            cwd=project_root,
            env=env,
        )

        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert any(tool.name == "health_check_tool" for tool in tools.tools)
                result = await session.call_tool("health_check_tool", {})
                payload = json.loads(result.content[0].text)
                assert payload["status"] == "ok"
                assert payload["table_count"] >= 1

    asyncio.run(run_check())
