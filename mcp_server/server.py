from __future__ import annotations

import argparse

from mcp.server.fastmcp import FastMCP

from mcp_server.tools.warehouse import (
    get_metric_definition,
    get_table_schema,
    health_check,
    list_tables,
    search_warehouse_docs,
    validate_sql,
)


mcp = FastMCP(
    "warehouse-agent-mcp",
    instructions=(
        "Local MCP server exposing mock warehouse metadata, metric definitions, "
        "knowledge-base search, and SQL validation tools for the warehouse agent MVP."
    ),
    host="127.0.0.1",
    port=8765,
    log_level="WARNING",
)


@mcp.tool()
def search_warehouse_docs_tool(query: str, top_k: int = 4):
    """Search warehouse standards, metric definitions, DQC templates, and table metadata."""
    return search_warehouse_docs(query=query, top_k=top_k)


@mcp.tool()
def get_metric_definition_tool(metric_name: str):
    """Return the mock definition, field mapping, and SQL expression for a metric."""
    return get_metric_definition(metric_name)


@mcp.tool()
def list_tables_tool(layer: str | None = None):
    """List known mock warehouse tables. Optionally filter by layer such as ODS, DWD, DWS, ADS, or DIM."""
    return list_tables(layer)


@mcp.tool()
def get_table_schema_tool(table_name: str):
    """Return the schema for a known mock warehouse table."""
    return get_table_schema(table_name)


@mcp.tool()
def validate_sql_tool(ddl: str, etl_sql: str, parsed_requirement: dict | str):
    """Validate generated DDL and ETL SQL against the parsed report requirement."""
    return validate_sql(ddl=ddl, etl_sql=etl_sql, parsed_requirement=parsed_requirement)


@mcp.tool()
def health_check_tool():
    """Return MCP server health and mock knowledge-base counts."""
    return health_check()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the warehouse agent local MCP server.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport to use. Default is stdio for local clients.",
    )
    args = parser.parse_args()
    mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
