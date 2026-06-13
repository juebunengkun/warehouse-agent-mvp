# Warehouse Agent MVP

一个面向数据开发场景的 **Report-to-Warehouse Modeling Agent**：

> 自然语言报表需求 -> 指标/维度解析 -> 人工确认 -> 元数据/RAG 工具检索 -> ODS/DWD/DWS/ADS 建模方案 -> DDL/ETL SQL/DQC -> SQL 自检。

当前项目仍是 MVP，但已经具备 Agent 雏形：LangGraph 状态机、工具调用、人工确认、SQL 校验和修正回路。

## Screenshots

![Home](docs/home.svg)

![Generated Report](docs/generated-report.svg)

真实 PNG 截图生成方式见 [docs/screenshots.md](docs/screenshots.md)。

## Features

- 解析自然语言报表需求，抽取指标、维度、粒度、刷新周期。
- 在生成前让用户确认或修改结构化需求。
- 检索本地模拟知识库，包括数仓规范、指标口径、历史表结构、DQC 模板。
- 生成 ODS、DWD、DWS、ADS 建模方案。
- 生成 Hive 风格 DDL、ETL SQL、DQC 规则。
- 记录工具调用轨迹，并对生成 SQL 做基础自检。
- 暴露本地 MCP Server，提供元数据、指标口径、知识库检索和 SQL 校验工具。
- 无 API Key 也能跑 demo；配置 API Key 后需求解析会优先调用 LLM。

## Architecture

```mermaid
flowchart TD
    A["User report requirement"] --> B["Parse requirement"]
    B --> C{"Need confirmation?"}
    C -->|Yes| D["Human confirmation / edit"]
    D --> E["Retrieve context"]
    C -->|No| E
    E --> F["Knowledge search tool"]
    E --> G["Metric lookup tool"]
    E --> H["Metadata lookup tool"]
    F --> I["Generate modeling plan"]
    G --> I
    H --> I
    I --> J["Generate DDL"]
    J --> K["Generate ETL SQL"]
    K --> L["SQL validation tool"]
    L -->|Failed| M["Rewrite SQL once"]
    M --> L
    L -->|Passed or max retry| N["Generate DQC"]
    N --> O["Review and final report"]
```

更多设计说明见 [docs/architecture.md](docs/architecture.md)。

## Quick Start

在本目录执行：

```powershell
.\run_demo.ps1
```

启动页面：

```powershell
.\run_app.ps1
```

打开：

```text
http://127.0.0.1:8501
```

当前工作区路径包含中文，部分 `uv` 版本在 Windows 下写 `uv.lock` 可能失败，所以提供了 PowerShell 启动脚本。英文路径下也可以直接使用：

```powershell
uv run warehouse-agent --demo
uv run streamlit run app.py
```

## LLM Config

复制或编辑 `.env`：

```text
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5.5
WAREHOUSE_AGENT_USE_LLM=true
```

不要提交 `.env`，仓库只保留 `.env.example`。

测试 API：

```powershell
.\check_api.ps1
```

没有 API Key 时也可以运行，系统会使用规则和模板生成一个稳定演示结果。

## Local MCP Server

启动 stdio 模式 MCP Server：

```powershell
.\run_mcp.ps1
```

或者使用 Python：

```powershell
$env:PYTHONPATH="src;."
python -m mcp_server.server
```

暴露的 MCP Tools：

- `search_warehouse_docs_tool`
- `get_metric_definition_tool`
- `list_tables_tool`
- `get_table_schema_tool`
- `validate_sql_tool`
- `health_check_tool`

这些工具目前读取本地模拟知识库。后续可以替换成真实 Hive、DataHub、指标平台、SQL dry-run 服务或 DQC 平台。

## Tests

运行测试：

```powershell
.\run_tests.ps1
```

当前测试覆盖：

- 需求解析不会把“支付用户数”误判成“用户”维度。
- LangGraph 可以停在人工确认态。
- 人工确认后可以继续生成完整方案。
- SQL 自检能发现缺分区、缺 GROUP BY 等问题。
- MCP 工具可以返回指标、表结构、知识库检索和 SQL 校验结果。
- 通过 MCP stdio client 启动本地 MCP Server 并调用 `health_check_tool`。

## Project Structure

```text
warehouse_agent_mvp/
  app.py
  mcp_server/
    server.py
    tools/
      warehouse.py
  knowledge_base/
    warehouse_standards.md
    metric_definitions.md
    table_metadata.json
    dqc_templates.md
  src/dw_agent/
    graph.py
    state.py
    tools.py
    nodes/
  tests/
  docs/
```

## Current Limits

- 元数据是模拟 JSON，不是生产元数据平台。
- RAG 是关键词检索，不是向量库。
- SQL 自检是规则校验，不是真实 SQL dry-run。
- DQC 规则是模板生成，还没有接入真实 DQC 平台。
- 生成 SQL 是初稿，真实落地前仍需人工 review。

## Roadmap

- 接入真实 Hive/Glue/DataHub/元数据平台。
- 将本地工具调用切换为 MCP client 调用 MCP Server。
- 把 RAG 从关键词检索升级为向量检索。
- 增加 SQL parser / dry-run 校验。
- 增加调度 DAG 生成。
- 增加 CI，自动跑测试和 lint。
