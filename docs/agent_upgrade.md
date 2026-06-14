# Controlled Data Warehouse Agent Upgrade

## Why The Previous Version Looked More Like A Workflow

The earlier MVP already had useful data-development steps: requirement parsing,
context retrieval, table reuse decisions, modeling strategy generation, DDL/ETL
generation, SQL validation, SQL style review, DQC generation, and a final report.

However, the control path was mostly fixed:

```text
parse -> retrieve -> reuse -> modeling -> ddl -> etl -> validate -> review
```

That made it useful as a Report-to-Warehouse workflow, but less agent-like. A
more convincing agent should make its plan explicit, decide which tools are
needed, verify intermediate results, retry within limits, and clearly mark
questions that need human judgment.

## What Controlled Data Warehouse Agent Means

This project is now positioned as a Controlled Data Warehouse Agent MVP. It is
not a fully autonomous production agent. It is a bounded, inspectable agent that
can:

- create an explicit plan before generation,
- route metadata and validation tools based on current state,
- preserve human-in-the-loop clarification points,
- run read-only SQL preview when a local DuckDB demo is available,
- verify generated outputs before final reporting,
- rewrite SQL within a strict retry limit,
- explain tool calls and verification results in the final report.

## New Control Nodes

### Planner

`plan_task` reads the parsed requirement and produces `state["agent_plan"]`.
The plan includes:

- goal,
- required steps,
- tools needed,
- risk notes,
- whether clarification is needed.

The planner does not generate SQL. It only describes the next actions the agent
expects to take.

### Clarification

`clarify_requirement` writes `state["clarification"]`.

It records questions such as:

- whether payment amount is counted by order time or payment time,
- how new/existing users are classified,
- whether refund rate is amount-based or order-count-based,
- whether unknown dimensions need explicit mapping,
- whether the refresh cycle is T+1, hourly, real-time, weekly, or monthly.

In the MVP, the flow does not hard-stop on these questions. Instead, the final
report marks them as human-review requirements.

### Tool Router

`tool_router` writes:

- `state["tool_calls"]`,
- `state["tool_results"]`,
- `state["tool_errors"]`.

It calls metadata through `MetadataProvider` only. It does not read
`table_metadata.json` directly. This keeps the agent compatible with
`LocalJsonMetadataProvider`, `InformationSchemaMetadataProvider`, and future
metadata backends.

### SQL Preview

`sql_preview` runs only for the local DuckDB information_schema demo.

Safety rules:

- SELECT/WITH only,
- no INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE/OVERWRITE/MSCK/REPAIR/CALL,
- no multi-statement execution,
- automatic `LIMIT 100`,
- read-only DuckDB connection,
- structured errors returned into state instead of crashing the graph.

The preview returns columns, sampled rows, row count, null-rate summary, warnings,
and errors.

### Verifier

`verify_outputs` writes `state["verification_result"]`.

It summarizes:

- SQL parser/static validation status,
- SQL style review status,
- SQL preview status,
- DQC generation status,
- modeling strategy status,
- blocking issues,
- warnings,
- whether rewrite is needed,
- whether human review is needed,
- suggested next action.

The verifier is used once inside the validation subgraph to decide whether to
rewrite SQL, and once after DQC generation so the final report can show a
complete verification state.

## Rewrite Limit

`rewrite_sql` now maintains `state["rewrite_count"]`. The default maximum is one
rewrite attempt. This avoids infinite repair loops while still allowing the
agent to respond to SQL validation, SQL style, or SQL preview failures.

If the rewrite limit is reached, the agent records a skipped rewrite action and
requires human review.

## Human-In-The-Loop Design

The MVP intentionally does not auto-resolve high-risk business semantics.
Questions about metric definitions, user classification, refund-rate formulas,
and reusable table grain are surfaced in the final report.

This is important because warehouse modeling decisions often encode business
contracts. The agent can draft and verify, but production usage still requires
review.

## Future Integration Path

The same control layer can later connect to:

- real MCP servers,
- metric platforms,
- Hive Metastore or Trino/Iceberg catalogs,
- DataHub or OpenMetadata,
- dbt manifest/catalog,
- SQL dry-run or explain platforms,
- scheduler systems such as Airflow or DolphinScheduler,
- approval and permission platforms.

The current design keeps those integrations behind provider/tool interfaces so
the main graph remains inspectable.
