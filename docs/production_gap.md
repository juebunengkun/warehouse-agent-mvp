# MVP 与生产数仓平台差距

当前项目适合作为 Report-to-Warehouse Modeling Agent 的原型，但距离生产级数仓平台还有明显差距。

## 元数据

- 当前：本地 `knowledge_base/table_metadata.json`。
- 生产：应接入 DataHub、Hive Metastore、Glue 或内部元数据平台，实时读取表、字段、分区、血缘、Owner、SLA、认证状态。

## 指标口径

- 当前：Markdown 和 Python 字典模拟指标口径。
- 生产：应接入指标平台，读取指标定义、口径版本、适用粒度、负责人和审批状态。

## SQL 校验

- 当前：`sqlglot` + 规则校验。
- 生产：应接入真实 Hive/Spark dry-run、`EXPLAIN`、字段权限校验和分区可用性检查。

## 调度

- 当前：只生成 SQL 和建议。
- 生产：应生成 Airflow、DolphinScheduler 或内部调度平台 DAG，并校验依赖和 SLA。

## DQC

- 当前：模板化 DQC 规则。
- 生产：应接入 DQC 平台，生成可执行规则、告警策略、负责人和阻断策略。

## 权限

- 当前：本地模拟，无权限控制。
- 生产：需要表权限、字段权限、敏感字段识别、脱敏策略和审计记录。

## 代码生成

- 当前：SQL 仍需人工 review。
- 生产：需要 CI、lint、dry-run、CR 流程、回滚策略和发布审批。
