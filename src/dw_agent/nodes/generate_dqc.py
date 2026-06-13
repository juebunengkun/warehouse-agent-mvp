from __future__ import annotations

from dw_agent.nodes.common import group_fields, markdown_table, metric_columns, table_names
from dw_agent.state import AgentState


def generate_dqc(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    names = table_names(parsed)
    strategy = state.get("modeling_strategy", {})
    dws_table = _summary_table_name(strategy, names["dws"])
    ads_table = _application_table_name(strategy, names["ads"])
    group_by = group_fields(parsed)
    metric_fields = [field for _, field, _, _ in metric_columns(parsed.get("metrics", []))]
    key_expr = ", ".join(group_by) if group_by else "dt"
    join_condition = " AND ".join([f"d.{field} = a.{field}" for field in group_by] + ["d.dt = a.dt"])
    metric_mismatch = " OR\n  ".join([f"COALESCE(d.{field}, 0) <> COALESCE(a.{field}, 0)" for field in metric_fields])

    rows = [
        ["分区完整性", names["dwd"], "当日分区记录数 > 0", "阻断"],
        ["主键/粒度唯一", dws_table, f"{key_expr} 在同一 dt 下唯一", "阻断"],
        ["维度非空", dws_table, f"{key_expr} 不为空", "阻断"],
        ["指标非负", dws_table, "金额、次数、人数类指标 >= 0", "阻断"],
        ["波动监控", ads_table, "核心指标日环比波动超过 40% 告警", "告警"],
        ["层间一致", f"{dws_table} vs {ads_table}", "ADS 应按同一粒度与 DWS 指标一致", "阻断"],
    ]

    metric_checks = "\n".join(
        [
            f"SELECT COUNT(1) AS bad_rows FROM {dws_table} WHERE dt='${{bizdate}}' AND {field} < 0;"
            for field in metric_fields
        ]
    )

    dqc = f"""## DQC 规则

{markdown_table(["规则类型", "检查表", "检查逻辑", "处理级别"], rows)}

### 示例检查 SQL

```sql
-- 1. 分区完整性
SELECT COUNT(1) AS row_count
FROM {names["dwd"]}
WHERE dt='${{bizdate}}';

-- 2. 粒度唯一性
SELECT {key_expr}, COUNT(1) AS cnt
FROM {dws_table}
WHERE dt='${{bizdate}}'
GROUP BY {key_expr}
HAVING COUNT(1) > 1;

-- 3. 指标非负
{metric_checks}

-- 4. ADS 与 DWS 汇总一致性
SELECT
  COUNT(1) AS mismatch_rows
FROM {dws_table} d
FULL OUTER JOIN {ads_table} a
  ON {join_condition}
WHERE COALESCE(d.dt, a.dt)='${{bizdate}}'
  AND (
  {metric_mismatch}
  );
```
"""
    return {**state, "dqc_rules": dqc}


def _summary_table_name(strategy: dict, fallback: str) -> str:
    summary_tables = strategy.get("summary_tables", [])
    if summary_tables:
        return summary_tables[0].get("name", fallback)
    return fallback


def _application_table_name(strategy: dict, fallback: str) -> str:
    application_tables = strategy.get("application_tables", [])
    if application_tables:
        return application_tables[0].get("name", fallback)
    return fallback
