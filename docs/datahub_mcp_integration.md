# DataHub MCP Integration

This project can optionally use DataHub as an external data map / metadata
platform. The integration is intentionally disabled by default so the MVP still
runs with local JSON metadata or local `information_schema` metadata.

Official references:

- DataHub quickstart: <https://docs.datahub.com/docs/quickstart>
- DataHub datapacks: <https://docs.datahub.com/docs/cli-commands/datapack>
- DataHub MCP server: <https://docs.datahub.com/docs/features/feature-guides/mcp>

## What This Adds

When `WAREHOUSE_METADATA_PROVIDER=datahub_mcp`, the agent can use DataHub MCP
metadata to improve:

- asset discovery for existing datasets,
- dataset schema lookup,
- upstream/downstream lineage context,
- owner and stewardship context,
- tags, glossary terms, domains, and data products,
- trusted/certified table signals used by table reuse decisions.

The integration does not make production changes in DataHub. It only uses
read-only metadata context. Metric semantics, reuse decisions, and generated SQL
still require human review before production use.

## Start DataHub Locally

Install the DataHub CLI and start the local Docker quickstart:

```powershell
python -m pip install acryl-datahub
datahub docker quickstart
```

After the quickstart finishes:

- UI: `http://localhost:9002`
- Default username: `datahub`
- Default password: `datahub`

Configure the CLI to talk to your local DataHub:

```powershell
datahub init --username datahub --password datahub
```

Load a richer demo metadata graph:

```powershell
datahub datapack load showcase-ecommerce
```

The `showcase-ecommerce` datapack contains many demo entities across warehouse,
BI, lineage, governance, glossary, domains, and data products. It is useful for
testing whether the agent can search existing assets and inspect schema/lineage
context.

## Create an Access Token

For a local or self-hosted DataHub instance, create a personal access token in
DataHub and keep it outside git.

Recommended local environment:

```powershell
$env:DATAHUB_GMS_URL="http://localhost:8080"
$env:DATAHUB_GMS_TOKEN="<your-datahub-personal-access-token>"
```

Never commit the token to `.env`, README, screenshots, logs, or test fixtures.
Use `.env.example` only as a placeholder reference.

## DataHub MCP Server Config

The self-hosted DataHub MCP server runs through `uvx`:

```json
{
  "mcpServers": {
    "datahub": {
      "command": "uvx",
      "args": ["mcp-server-datahub@latest"],
      "env": {
        "DATAHUB_GMS_URL": "http://localhost:8080",
        "DATAHUB_GMS_TOKEN": "<your-datahub-token>"
      }
    }
  }
}
```

This project starts the MCP server from Python using the same values:

```powershell
$env:WAREHOUSE_METADATA_PROVIDER="datahub_mcp"
$env:DATAHUB_MCP_ENABLED="true"
$env:DATAHUB_GMS_URL="http://localhost:8080"
$env:DATAHUB_GMS_TOKEN="<your-datahub-token>"
$env:DATAHUB_MCP_COMMAND="uvx"
$env:DATAHUB_MCP_PACKAGE="mcp-server-datahub@latest"
$env:DATAHUB_TIMEOUT="10"
```

The example YAML is available at
[`config/datahub_mcp.example.yml`](../config/datahub_mcp.example.yml).

## Agent Tool Mapping

The agent exposes stable internal tool names:

- `search_datahub_assets`
- `get_datahub_dataset_schema`
- `get_datahub_lineage`
- `get_datahub_ownership`
- `get_datahub_tags_and_terms`

The wrapper maps those names to DataHub MCP read-only tools where available:

- `search`
- `get_entities`
- `list_schema_fields`
- `get_lineage`

This keeps the LangGraph nodes stable even if the external MCP server uses a
slightly different tool naming convention.

## Run With DataHub MCP

Start the Streamlit app:

```powershell
.\run_app.ps1
```

Use a requirement that asks for existing metadata, owners, lineage, or trusted
tables. For example:

```text
Build a channel operation daily report. Before creating new DWS tables, search
DataHub for reusable certified tables, inspect schema, owner, glossary terms,
and upstream lineage. Metrics include pay amount, refund amount, order count,
visit user count, click user count, and pay conversion rate. Dimensions include
date, channel, region, new/existing user, and member level. Refresh is T+1.
```

The final report includes a `DataHub MCP Context` section. If DataHub MCP is
disabled, the section says it was skipped. If enabled, the section summarizes
matched assets, fields, owners, tags/glossary terms, and lineage counts.

## Test Strategy

The automated tests use mocks only. They do not require Docker, a live DataHub
instance, network access, or real tokens.

Run:

```powershell
uv run pytest tests/test_datahub_mcp_provider.py tests/test_datahub_mcp_tool.py tests/test_tool_router_datahub.py
```

Run the full project checks:

```powershell
.\run_quality.ps1
```

## Security Notes

- `DATAHUB_GMS_TOKEN` is required only when DataHub MCP is enabled.
- Token values are never written to the final report.
- Structured client errors redact token values before returning them.
- Tests must use mocked MCP responses and placeholder token values only.
- Mutation tools such as tag/owner updates are not used by this project.
