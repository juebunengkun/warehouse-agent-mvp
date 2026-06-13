from __future__ import annotations

import os
from pathlib import Path


def main() -> None:
    try:
        import duckdb
    except ModuleNotFoundError as exc:
        raise SystemExit("DuckDB is not installed. Install project dependencies, then rerun this script.") from exc

    demo_dir = Path(__file__).resolve().parent
    db_path = Path(os.getenv("WAREHOUSE_DUCKDB_PATH") or demo_dir / "warehouse_demo.duckdb")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    schema_path = demo_dir / "demo_schema.sql"

    conn = duckdb.connect(str(db_path))
    try:
        conn.execute(schema_path.read_text(encoding="utf-8"))
        _insert_sample_data(conn)
    finally:
        conn.close()

    print(f"Created DuckDB demo database: {db_path}")


def _insert_sample_data(conn) -> None:
    conn.execute("DELETE FROM dim_channel_df")
    conn.execute("DELETE FROM dim_region_df")
    conn.execute("DELETE FROM dim_user_profile_df")
    conn.execute("DELETE FROM dim_category_df")
    conn.execute("DELETE FROM dwd_sales_detail_di")
    conn.execute("DELETE FROM dwd_user_behavior_event_di")
    conn.execute("DELETE FROM dws_category_channel_day_summary_di")
    conn.execute("DELETE FROM ads_category_operation_daily_report_di")

    conn.executemany(
        "INSERT INTO dim_channel_df VALUES (?, ?, ?, ?)",
        [
            ("ch_app", "App", "owned", "2026-06-12"),
            ("ch_search", "Search", "paid", "2026-06-12"),
        ],
    )
    conn.executemany(
        "INSERT INTO dim_region_df VALUES (?, ?, ?, ?)",
        [
            ("r_sh", "Shanghai", "Shanghai", "2026-06-12"),
            ("r_hz", "Zhejiang", "Hangzhou", "2026-06-12"),
        ],
    )
    conn.executemany(
        "INSERT INTO dim_user_profile_df VALUES (?, ?, ?, ?)",
        [
            ("u001", "new", "gold", "2026-06-12"),
            ("u002", "existing", "silver", "2026-06-12"),
        ],
    )
    conn.executemany(
        "INSERT INTO dim_category_df VALUES (?, ?, ?, ?)",
        [
            ("cat_phone", "Electronics", "Phone", "2026-06-12"),
            ("cat_food", "Grocery", "Snack", "2026-06-12"),
        ],
    )
    conn.executemany(
        "INSERT INTO dwd_sales_detail_di VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "o001",
                "u001",
                "sku001",
                "cat_phone",
                "ch_app",
                "r_sh",
                1999.00,
                0.00,
                "PAID",
                "2026-06-12 10:00:00",
                None,
                "2026-06-12",
            ),
            (
                "o002",
                "u002",
                "sku002",
                "cat_food",
                "ch_search",
                "r_hz",
                59.90,
                9.90,
                "REFUNDED",
                "2026-06-12 11:00:00",
                "2026-06-12 18:00:00",
                "2026-06-12",
            ),
        ],
    )
    conn.executemany(
        "INSERT INTO dwd_user_behavior_event_di VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            ("e001", "u001", "sku001", "cat_phone", "ch_app", "exposure", "2026-06-12 09:00:00", "2026-06-12"),
            ("e002", "u001", "sku001", "cat_phone", "ch_app", "click", "2026-06-12 09:02:00", "2026-06-12"),
            ("e003", "u002", "sku002", "cat_food", "ch_search", "cart", "2026-06-12 10:20:00", "2026-06-12"),
        ],
    )
    conn.executemany(
        "INSERT INTO dws_category_channel_day_summary_di VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "2026-06-12",
                "cat_phone",
                "Electronics",
                "Phone",
                "ch_app",
                "App",
                "owned",
                "new",
                "gold",
                120,
                1000,
                230,
                45,
                35,
                20,
                22,
                39980.00,
                1,
                1999.00,
                "2026-06-12",
            )
        ],
    )
    conn.executemany(
        "INSERT INTO ads_category_operation_daily_report_di VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                "2026-06-12",
                "Electronics",
                "Phone",
                "App",
                "owned",
                "new",
                "gold",
                120,
                1000,
                230,
                45,
                35,
                20,
                22,
                39980.00,
                1,
                1999.00,
                0.23,
                0.20,
                0.57,
                1817.27,
                0.05,
                "2026-06-12",
            )
        ],
    )


if __name__ == "__main__":
    main()
