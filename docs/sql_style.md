# SQL 书写规范

目标不是禁止 `WITH AS`，而是避免生成一大段临时 CTE，导致粒度、分区、口径和血缘不可控。

## 基础规则

1. 禁止 `SELECT *`。
2. CTE 最多 3 层，超过 3 层必须拆成 DWD/DWS/ADS 或可复用中间表。
3. CTE 命名必须有业务含义，禁止 `base`、`tmp`、`t1`、`t2`、`final`、`result` 这类无意义名称。
4. 每个 `INSERT` 前必须写注释说明目标表粒度。
5. 每个 `JOIN` 必须显式写关联键。
6. 事实表关联维表默认 `LEFT JOIN`，避免维度缺失导致事实数据被过滤。
7. 维表 join 必须带分区条件，例如 `dim.dt='${bizdate}'`。
8. `WHERE dt='${bizdate}'` 要尽量下推到最早的上游表。
9. 聚合 SQL 必须显式 `GROUP BY` 所有目标粒度字段。
10. 派生指标必须处理除零，例如 `CASE WHEN denominator = 0 THEN 0 ELSE numerator / denominator END` 或 `NULLIF`。
11. 金额字段统一 `DECIMAL`，不要直接用 `DOUBLE`。
12. DWS/ADS `INSERT` 必须显式写 `PARTITION`。
13. 指标口径不能在 ADS 重复散落计算，公共指标优先沉淀到 DWS。

## 推荐形态

- DWD：清洗事实字段，关联必要 DIM，保留事件明细粒度。
- DWS：按稳定业务粒度沉淀公共指标。
- ADS：面向具体报表消费，从 DWS 取数，尽量少做复杂口径计算。

## 审查范围

MVP 阶段通过 `sqlglot` 和正则做风格审查，重点识别阻断问题：

- `SELECT *`
- 过多 CTE
- 无意义 CTE 名称
- `JOIN` 缺少 `ON`
- DIM join 缺少分区条件
- DIM 使用 `INNER JOIN`
- 聚合与非聚合字段混用但无 `GROUP BY`
- 除法缺少除零保护
- `INSERT` 目标表缺少 `PARTITION`
