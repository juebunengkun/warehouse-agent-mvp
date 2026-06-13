from __future__ import annotations

from dw_agent.metadata import load_table_metadata
from dw_agent.nodes.common import dimension_columns, metric_columns, table_names
from dw_agent.state import AgentState


def generate_ddl(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    names = table_names(parsed)
    strategy = state.get("modeling_strategy", {})
    dims = dimension_columns(parsed.get("dimensions", []))
    metrics = metric_columns(parsed.get("metrics", []))
    report_columns = [(field, sql_type, comment) for _, field, sql_type, comment in dims + metrics]

    sections = [
        _event_table_ddl(names["ods"], "ODS 原始业务事件表"),
        *_dim_table_ddls(strategy.get("dim_tables", []), state.get("knowledge_base_path")),
        _event_table_ddl(names["dwd"], "DWD 清洗后业务明细事实表", dwd=True),
    ]

    if _reuse_dws(strategy):
        reuse_table = strategy.get("summary_tables", [{}])[0].get("name", "")
        sections.append(f"-- DWS: 复用已有公共汇总表 {reuse_table}，不重复生成 DDL。")
    else:
        sections.append(_report_table_ddl(names["dws"], "DWS 主题粒度汇总表", report_columns))

    ads_table = _ads_table_name(strategy, names["ads"])
    ads_columns = [*report_columns, ("update_time", "STRING", "数据更新时间")]
    sections.append(_report_table_ddl(ads_table, "ADS 报表应用层结果表", ads_columns))

    return {**state, "ddl": "\n\n".join(sections) + "\n"}


def _event_table_ddl(table_name: str, comment: str, *, dwd: bool = False) -> str:
    tail_fields = (
        "  pay_time STRING COMMENT '支付时间',\n  stat_date STRING COMMENT '统计日期'"
        if dwd
        else "  event_time STRING COMMENT '业务事件时间',\n  is_valid TINYINT COMMENT '是否有效记录'"
    )
    return f"""CREATE TABLE IF NOT EXISTS {table_name} (
  order_id STRING COMMENT '订单 ID',
  user_id STRING COMMENT '用户 ID',
  sku_id STRING COMMENT '商品 SKU ID',
  gmv_amount DECIMAL(18,2) COMMENT '下单 GMV',
  pay_amount DECIMAL(18,2) COMMENT '支付金额',
  discount_amount DECIMAL(18,2) COMMENT '优惠金额',
  refund_amount DECIMAL(18,2) COMMENT '退款金额',
  order_status STRING COMMENT '订单状态',
  exposure_user_id STRING COMMENT '曝光用户 ID',
  click_user_id STRING COMMENT '点击用户 ID',
  order_user_id STRING COMMENT '下单用户 ID',
  channel_id STRING COMMENT '渠道 ID',
  channel_name STRING COMMENT '渠道名称',
  channel_type STRING COMMENT '渠道类型',
  region_id STRING COMMENT '地区 ID',
  region_name STRING COMMENT '地区名称',
  province_name STRING COMMENT '省份名称',
  city_name STRING COMMENT '城市名称',
  user_type STRING COMMENT '新老用户标识',
  member_level STRING COMMENT '会员等级',
{tail_fields}
)
COMMENT '{comment}'
PARTITIONED BY (dt STRING COMMENT '分区日期')
STORED AS ORC;"""


def _dim_table_ddls(dim_tables: list[dict], kb_path: str | None) -> list[str]:
    metadata = {table["name"]: table for table in load_table_metadata(kb_path)}
    ddls = []
    for table in dim_tables:
        table_meta = metadata.get(table["name"])
        if not table_meta:
            continue
        fields = [
            (field["name"], field["type"], field.get("comment", ""))
            for field in table_meta.get("fields", [])
            if field.get("name") != table_meta.get("partition_key", "dt")
        ]
        ddls.append(_generic_table_ddl(table["name"], table.get("description", "DIM 维度表"), fields))
    return ddls


def _report_table_ddl(table_name: str, comment: str, columns: list[tuple[str, str, str]]) -> str:
    return _generic_table_ddl(table_name, comment, columns)


def _generic_table_ddl(table_name: str, comment: str, columns: list[tuple[str, str, str]]) -> str:
    return f"""CREATE TABLE IF NOT EXISTS {table_name} (
{_format_columns(columns)}
)
COMMENT '{comment}'
PARTITIONED BY (dt STRING COMMENT '分区日期')
STORED AS ORC;"""


def _format_columns(columns: list[tuple[str, str, str]]) -> str:
    lines = []
    for index, (field, sql_type, comment) in enumerate(columns):
        comma = "," if index < len(columns) - 1 else ""
        lines.append(f"  {field} {sql_type} COMMENT '{comment}'{comma}")
    return "\n".join(lines)


def _reuse_dws(strategy: dict) -> bool:
    return bool(strategy.get("summary_tables") and strategy.get("summary_tables", [{}])[0].get("reuse"))


def _ads_table_name(strategy: dict, fallback: str) -> str:
    app_tables = strategy.get("application_tables", [])
    if app_tables:
        return app_tables[0].get("name", fallback)
    return fallback
