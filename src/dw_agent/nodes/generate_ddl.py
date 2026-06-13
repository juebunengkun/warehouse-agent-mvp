from __future__ import annotations

from dw_agent.nodes.common import dimension_columns, metric_columns, table_names
from dw_agent.state import AgentState


def generate_ddl(state: AgentState) -> AgentState:
    parsed = state["parsed"]
    names = table_names(parsed)
    dims = dimension_columns(parsed.get("dimensions", []))
    metrics = metric_columns(parsed.get("metrics", []))

    dws_columns = _format_columns([(field, sql_type, comment) for _, field, sql_type, comment in dims + metrics])

    ddl = f"""-- ODS: 原始事件表
CREATE TABLE IF NOT EXISTS {names["ods"]} (
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
  event_time STRING COMMENT '业务事件时间',
  is_valid TINYINT COMMENT '是否有效记录'
)
COMMENT 'ODS 原始业务事件表'
PARTITIONED BY (dt STRING COMMENT '分区日期')
STORED AS ORC;

-- DWD: 清洗后的明细事实表
CREATE TABLE IF NOT EXISTS {names["dwd"]} (
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
  pay_time STRING COMMENT '支付时间',
  stat_date STRING COMMENT '统计日期'
)
COMMENT 'DWD 清洗后业务明细事实表'
PARTITIONED BY (dt STRING COMMENT '分区日期')
STORED AS ORC;

-- DWS: 按报表粒度聚合的主题汇总表
CREATE TABLE IF NOT EXISTS {names["dws"]} (
{dws_columns}
)
COMMENT 'DWS 主题粒度汇总表'
PARTITIONED BY (dt STRING COMMENT '分区日期')
STORED AS ORC;

-- ADS: 面向报表查询的应用层表
CREATE TABLE IF NOT EXISTS {names["ads"]} (
{dws_columns},
  update_time STRING COMMENT '数据更新时间'
)
COMMENT 'ADS 报表应用层结果表'
PARTITIONED BY (dt STRING COMMENT '分区日期')
STORED AS ORC;
"""
    return {**state, "ddl": ddl}


def _format_columns(columns: list[tuple[str, str, str]]) -> str:
    lines = []
    for index, (field, sql_type, comment) in enumerate(columns):
        comma = "," if index < len(columns) - 1 else ""
        lines.append(f"  {field} {sql_type} COMMENT '{comment}'{comma}")
    return "\n".join(lines)
