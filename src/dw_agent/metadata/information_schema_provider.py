from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dw_agent.metadata.provider import (
    clone_table,
    field_names,
    metric_fields,
    metric_source_fields,
    normalize_grain,
    semantic_dimension_fields,
    table_matches_business_process,
)
from dw_agent.metadata.selector import (
    choose_best_tables,
    score_dimension_table,
    score_fact_table,
    score_summary_table,
)
from dw_agent.metadata.semantic_mapper import enrich_table_metadata


class InformationSchemaMetadataProvider:
    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}
        self.db_type = str(self.config.get("db_type") or os.getenv("WAREHOUSE_DB_TYPE") or "duckdb").lower()

    def list_tables(self) -> list[dict[str, Any]]:
        if self.db_type == "duckdb":
            return self._list_duckdb_tables()
        if self.db_type in {"postgres", "postgresql"}:
            return self._list_postgres_tables()
        if self.db_type == "mysql":
            return self._list_mysql_tables()
        raise ValueError(f"Unsupported WAREHOUSE_DB_TYPE={self.db_type!r}; expected duckdb, postgres, or mysql.")

    def get_table(self, table_name: str) -> dict[str, Any] | None:
        for table in self.list_tables():
            if table.get("name") == table_name:
                return table
        return None

    def search_tables(
        self,
        *,
        layer: str | None = None,
        table_type: str | None = None,
        business_process: str | None = None,
        fields: set[str] | list[str] | None = None,
        metrics: list[str] | None = None,
        grain: set[str] | list[str] | str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        requested_fields = set(fields or set()) | metric_fields(metrics or []) | metric_source_fields(metrics or [])
        requested_grain = normalize_grain(grain)
        scored = []
        for table in self.list_tables():
            if layer and str(table.get("layer", "")).upper() != layer.upper():
                continue
            if table_type and table.get("table_type") != table_type:
                continue
            if business_process and not table_matches_business_process(table, business_process):
                continue

            available_fields = field_names(table)
            table_grain = normalize_grain(table.get("grain", ""))
            covered = requested_fields & available_fields
            score = 0
            if requested_fields:
                score += int(60 * len(covered) / len(requested_fields))
            if requested_grain and requested_grain == table_grain:
                score += 18
            elif requested_grain and requested_grain.issubset(table_grain):
                score += 10
            if table.get("partition_key"):
                score += 6
            if table.get("primary_keys"):
                score += 4
            if table.get("source") == "information_schema":
                score += 2
            if not requested_fields:
                score += 1
            scored.append(
                {
                    **table,
                    "score": score,
                    "covered_fields": sorted(covered),
                    "missing_fields": sorted(requested_fields - available_fields),
                }
            )
        return choose_best_tables(scored, top_k=top_k)

    def search_dimensions(self, semantic_dimensions: list[str]) -> list[dict[str, Any]]:
        selected: dict[str, dict[str, Any]] = {}
        for dimension in semantic_dimensions:
            required_fields = semantic_dimension_fields([dimension])
            if required_fields == {"stat_date"}:
                continue
            scored = []
            for table in self.list_tables():
                result = score_dimension_table(table, dimension)
                if result["score"] <= 0 or not result["covered_fields"]:
                    continue
                scored.append({**table, **result})
            for table in choose_best_tables(scored, top_k=1):
                selected[str(table["name"])] = table
        return list(selected.values())

    def search_facts(self, metrics: list[str], business_process: str | None = None) -> list[dict[str, Any]]:
        scored = []
        for table in self.list_tables():
            if str(table.get("layer", "")).upper() != "DWD":
                continue
            if table.get("table_type") not in {"transaction_fact", "snapshot_fact", "event_fact", "detail_fact"}:
                continue
            result = score_fact_table(table, metrics, business_process)
            if result["score"] <= 0 or not result["covered_fields"]:
                continue
            scored.append({**table, **result})
        return choose_best_tables(scored, top_k=3)

    def search_summaries(
        self,
        dimensions: list[str],
        metrics: list[str],
        grain: set[str] | list[str] | str | None = None,
        business_process: str | None = None,
    ) -> list[dict[str, Any]]:
        scored = []
        for table in self.list_tables():
            if str(table.get("layer", "")).upper() not in {"DWS", "ADS"}:
                continue
            if table.get("table_type") not in {"summary_fact", "application_report"}:
                continue
            if business_process and not table_matches_business_process(table, business_process):
                continue
            result = score_summary_table(table, dimensions, metrics, grain, business_process)
            if result["score"] <= 0:
                continue
            scored.append({**table, **result})
        return choose_best_tables(scored, top_k=3)

    def _list_duckdb_tables(self) -> list[dict[str, Any]]:
        try:
            import duckdb
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "DuckDB metadata provider requires the 'duckdb' package. Install project dependencies."
            ) from exc

        db_path = Path(
            self.config.get("duckdb_path") or os.getenv("WAREHOUSE_DUCKDB_PATH") or "./demo/warehouse_demo.duckdb"
        )
        if not db_path.exists():
            raise FileNotFoundError(
                f"DuckDB database not found: {db_path}. Run 'python demo/init_duckdb_demo.py' first."
            )

        with duckdb.connect(str(db_path), read_only=True) as conn:
            tables = conn.execute("""
                SELECT table_catalog, table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('information_schema', 'pg_catalog')
                ORDER BY table_schema, table_name
                """).fetchall()
            primary_keys = self._duckdb_primary_keys(conn)
            result = []
            for database, schema, name in tables:
                fields = self._duckdb_columns(conn, schema, name)
                result.append(
                    enrich_table_metadata(
                        name=name,
                        database=database,
                        schema=schema,
                        fields=fields,
                        primary_keys=primary_keys.get((schema, name)),
                    )
                )
            return [clone_table(table) for table in result]

    def _duckdb_columns(self, conn: Any, schema: str, table_name: str) -> list[dict[str, Any]]:
        rows = conn.execute(
            """
            SELECT column_name, data_type, ordinal_position, is_nullable
            FROM information_schema.columns
            WHERE table_schema = ?
              AND table_name = ?
            ORDER BY ordinal_position
            """,
            [schema, table_name],
        ).fetchall()
        return [
            {
                "name": name,
                "type": data_type,
                "comment": None,
                "ordinal_position": ordinal,
                "nullable": nullable == "YES",
            }
            for name, data_type, ordinal, nullable in rows
        ]

    def _duckdb_primary_keys(self, conn: Any) -> dict[tuple[str, str], list[str]]:
        try:
            rows = conn.execute("""
                SELECT kcu.table_schema, kcu.table_name, kcu.column_name, kcu.ordinal_position
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                 AND tc.table_name = kcu.table_name
                WHERE tc.constraint_type = 'PRIMARY KEY'
                ORDER BY kcu.table_schema, kcu.table_name, kcu.ordinal_position
                """).fetchall()
        except Exception:
            return {}
        keys: dict[tuple[str, str], list[str]] = {}
        for schema, table_name, column_name, _ in rows:
            keys.setdefault((schema, table_name), []).append(column_name)
        return keys

    def _list_postgres_tables(self) -> list[dict[str, Any]]:
        try:
            import psycopg
        except ModuleNotFoundError as exc:
            raise RuntimeError("PostgreSQL metadata provider requires the optional 'psycopg' package.") from exc

        schema = self.config.get("schema") or os.getenv("WAREHOUSE_DB_SCHEMA") or "public"
        database = self._required_config("database", "WAREHOUSE_DB_NAME")
        user = self._required_config("user", "WAREHOUSE_DB_USER")
        with psycopg.connect(
            host=self.config.get("host") or os.getenv("WAREHOUSE_DB_HOST") or "localhost",
            port=int(self.config.get("port") or os.getenv("WAREHOUSE_DB_PORT") or 5432),
            dbname=database,
            user=user,
            password=self.config.get("password") or os.getenv("WAREHOUSE_DB_PASSWORD"),
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_catalog, table_schema, table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                    """,
                    (schema,),
                )
                tables = cur.fetchall()
                result = []
                for database, table_schema, name in tables:
                    fields = self._postgres_columns(cur, table_schema, name)
                    result.append(
                        enrich_table_metadata(name=name, database=database, schema=table_schema, fields=fields)
                    )
                return [clone_table(table) for table in result]

    def _postgres_columns(self, cur: Any, schema: str, table_name: str) -> list[dict[str, Any]]:
        cur.execute(
            """
            SELECT column_name, data_type, ordinal_position, is_nullable
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table_name),
        )
        return [
            {
                "name": name,
                "type": data_type,
                "comment": None,
                "ordinal_position": ordinal,
                "nullable": nullable == "YES",
            }
            for name, data_type, ordinal, nullable in cur.fetchall()
        ]

    def _list_mysql_tables(self) -> list[dict[str, Any]]:
        try:
            import pymysql
        except ModuleNotFoundError as exc:
            raise RuntimeError("MySQL metadata provider requires the optional 'pymysql' package.") from exc

        database = self._required_config("database", "WAREHOUSE_DB_NAME")
        user = self._required_config("user", "WAREHOUSE_DB_USER")
        with pymysql.connect(
            host=self.config.get("host") or os.getenv("WAREHOUSE_DB_HOST") or "localhost",
            port=int(self.config.get("port") or os.getenv("WAREHOUSE_DB_PORT") or 3306),
            user=user,
            password=self.config.get("password") or os.getenv("WAREHOUSE_DB_PASSWORD"),
            database=database,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_schema, table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                    """,
                    (database,),
                )
                tables = cur.fetchall()
                result = []
                for schema, name in tables:
                    fields = self._mysql_columns(cur, schema, name)
                    result.append(enrich_table_metadata(name=name, database=database, schema=schema, fields=fields))
                return [clone_table(table) for table in result]

    def _mysql_columns(self, cur: Any, schema: str, table_name: str) -> list[dict[str, Any]]:
        cur.execute(
            """
            SELECT column_name, data_type, ordinal_position, is_nullable, column_comment
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema, table_name),
        )
        return [
            {
                "name": name,
                "type": data_type,
                "comment": comment or None,
                "ordinal_position": ordinal,
                "nullable": nullable == "YES",
            }
            for name, data_type, ordinal, nullable, comment in cur.fetchall()
        ]

    def _required_config(self, key: str, env_name: str) -> str:
        value = self.config.get(key) or os.getenv(env_name)
        if not value:
            raise RuntimeError(f"{env_name} is required for {self.db_type} information_schema metadata provider.")
        return str(value)
