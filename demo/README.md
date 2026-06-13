# DuckDB Information Schema Demo

This demo creates a local DuckDB file with real warehouse-like tables. It is
used by `InformationSchemaMetadataProvider` to read table and column metadata
from `information_schema` instead of `knowledge_base/table_metadata.json`.

```powershell
python demo/init_duckdb_demo.py
```

Then run the agent with:

```powershell
$env:WAREHOUSE_METADATA_PROVIDER="information_schema"
$env:WAREHOUSE_DB_TYPE="duckdb"
$env:WAREHOUSE_DUCKDB_PATH="./demo/warehouse_demo.duckdb"
```

The generated `warehouse_demo.duckdb` file is ignored by git.
