# Python 代码规范

本项目是面向数仓开发的 Agent，不只是一次性脚本。代码应优先保持可维护、可测试、可扩展。

## 基本规则

- Python 文件必须保持正常多行可读格式，不要压缩成一行。
- 使用 `black`、`isort`、`ruff` 和 `mypy` 做基础治理。
- 新增逻辑必须配套单元测试，尤其是解析、建模策略、SQL 校验、表复用决策。
- 关键数据结构要有类型注解，复杂字典建议先约定字段结构。

## 节点职责

- LangGraph 节点函数只做编排：读 state、调用 planner/helper、写回 state。
- 不要把复杂业务规则硬编码在节点函数里。
- 复杂规则应放在独立 planner/helper 模块，或沉淀到 `knowledge_base/`。
- 单个函数不要过长；当函数同时做解析、打分、格式化输出时，应拆分。

## 数仓规则落点

- 指标字段、维度字段、表粒度、增全量策略等通用规则优先放到 `knowledge_base/` 或公共 helper。
- 生成节点可以使用模板，但模板要读取 `modeling_strategy`，不要直接从自然语言需求硬拼 SQL。
- 表复用必须解释字段、粒度、业务过程、分区、SLA、认证状态，而不是只返回一个表名。

## 本地质量检查

```powershell
.\run_quality.ps1
```

等价命令：

```powershell
black .
isort .
ruff check .
mypy src mcp_server
pytest
```
