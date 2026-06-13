from __future__ import annotations

from typing import Any

TOPIC_CODES = {
    "销售": "sales",
    "交易": "trade",
    "订单": "trade",
    "用户": "user",
    "流量": "traffic",
    "商品": "product",
    "库存": "inventory",
    "营销": "marketing",
    "财务": "finance",
}

DIMENSION_COLUMNS = {
    "日期": [("stat_date", "STRING", "统计日期，格式 yyyy-MM-dd")],
    "地区": [
        ("region_id", "STRING", "地区 ID"),
        ("region_name", "STRING", "地区名称"),
    ],
    "渠道": [
        ("channel_id", "STRING", "渠道 ID"),
        ("channel_name", "STRING", "渠道名称"),
    ],
    "渠道类型": [("channel_type", "STRING", "渠道类型")],
    "省份": [("province_name", "STRING", "省份名称")],
    "城市": [("city_name", "STRING", "城市名称")],
    "新老用户": [("user_type", "STRING", "新老用户标识")],
    "会员等级": [("member_level", "STRING", "会员等级")],
    "商品": [
        ("sku_id", "STRING", "商品 SKU ID"),
        ("sku_name", "STRING", "商品名称"),
    ],
    "用户": [("user_id", "STRING", "用户 ID")],
}

METRIC_COLUMNS = {
    "曝光UV": ("exposure_uv", "BIGINT", "去重曝光用户数"),
    "点击UV": ("click_uv", "BIGINT", "去重点击用户数"),
    "下单用户数": ("order_user_count", "BIGINT", "去重下单用户数"),
    "销售额": ("sales_amount", "DECIMAL(18,2)", "支付成功订单金额汇总"),
    "GMV": ("gmv_amount", "DECIMAL(18,2)", "下单商品总金额"),
    "实付金额": ("pay_amount", "DECIMAL(18,2)", "支付成功订单实付金额"),
    "优惠金额": ("discount_amount", "DECIMAL(18,2)", "订单优惠金额"),
    "退款金额": ("refund_amount", "DECIMAL(18,2)", "退款发生日退款金额"),
    "订单数": ("order_count", "BIGINT", "去重订单数"),
    "支付订单数": ("pay_order_count", "BIGINT", "支付成功去重订单数"),
    "支付用户数": ("pay_user_count", "BIGINT", "去重支付用户数"),
    "客单价": ("avg_order_amount", "DECIMAL(18,2)", "销售额 / 订单数"),
    "支付转化率": ("pay_conversion_rate", "DECIMAL(18,6)", "支付用户数 / 点击UV"),
    "ARPU": ("arpu", "DECIMAL(18,2)", "实付金额 / 点击UV"),
    "转化率": ("conversion_rate", "DECIMAL(18,6)", "支付用户数 / 访问用户数"),
}

METRIC_SQL = {
    "曝光UV": "COUNT(DISTINCT exposure_user_id)",
    "点击UV": "COUNT(DISTINCT click_user_id)",
    "下单用户数": "COUNT(DISTINCT order_user_id)",
    "销售额": "SUM(CASE WHEN order_status IN ('PAID', 'FINISHED') THEN pay_amount ELSE 0 END)",
    "GMV": "SUM(gmv_amount)",
    "实付金额": "SUM(CASE WHEN order_status IN ('PAID', 'FINISHED') THEN pay_amount ELSE 0 END)",
    "优惠金额": "SUM(CASE WHEN order_status IN ('PAID', 'FINISHED') THEN discount_amount ELSE 0 END)",
    "退款金额": "SUM(refund_amount)",
    "订单数": "COUNT(DISTINCT CASE WHEN order_status IN ('PAID', 'FINISHED') THEN order_id END)",
    "支付订单数": "COUNT(DISTINCT CASE WHEN order_status IN ('PAID', 'FINISHED') THEN order_id END)",
    "支付用户数": "COUNT(DISTINCT CASE WHEN order_status IN ('PAID', 'FINISHED') THEN user_id END)",
    "客单价": "CASE WHEN COUNT(DISTINCT CASE WHEN order_status IN ('PAID', 'FINISHED') THEN order_id END) = 0 THEN 0 ELSE SUM(CASE WHEN order_status IN ('PAID', 'FINISHED') THEN pay_amount ELSE 0 END) / COUNT(DISTINCT CASE WHEN order_status IN ('PAID', 'FINISHED') THEN order_id END) END",
    "支付转化率": "CASE WHEN COUNT(DISTINCT click_user_id) = 0 THEN 0 ELSE COUNT(DISTINCT CASE WHEN order_status IN ('PAID', 'FINISHED') THEN user_id END) / COUNT(DISTINCT click_user_id) END",
    "ARPU": "CASE WHEN COUNT(DISTINCT click_user_id) = 0 THEN 0 ELSE SUM(CASE WHEN order_status IN ('PAID', 'FINISHED') THEN pay_amount ELSE 0 END) / COUNT(DISTINCT click_user_id) END",
    "转化率": "CASE WHEN COUNT(DISTINCT visit_user_id) = 0 THEN 0 ELSE COUNT(DISTINCT user_id) / COUNT(DISTINCT visit_user_id) END",
}


def topic_code(parsed: dict[str, Any]) -> str:
    theme = parsed.get("business_theme", "")
    for key, value in TOPIC_CODES.items():
        if key in theme:
            return value
    return "report"


def metric_columns(metrics: list[str]) -> list[tuple[str, str, str, str]]:
    columns: list[tuple[str, str, str, str]] = []
    for metric in metrics:
        field, sql_type, comment = METRIC_COLUMNS.get(
            metric,
            (f"metric_{len(columns) + 1}", "DECIMAL(18,4)", f"{metric}，需补充口径"),
        )
        columns.append((metric, field, sql_type, comment))
    return columns


def dimension_columns(dimensions: list[str]) -> list[tuple[str, str, str, str]]:
    columns: list[tuple[str, str, str, str]] = []
    for dimension in dimensions:
        for field, sql_type, comment in DIMENSION_COLUMNS.get(
            dimension,
            [(f"dim_{len(columns) + 1}", "STRING", f"{dimension}，需补充维表映射")],
        ):
            columns.append((dimension, field, sql_type, comment))
    return columns


def group_fields(parsed: dict[str, Any]) -> list[str]:
    return [field for _, field, _, _ in dimension_columns(parsed.get("dimensions", []))]


def metric_expression(metric: str) -> str:
    return METRIC_SQL.get(metric, f"SUM({metric})")


def table_names(parsed: dict[str, Any]) -> dict[str, str]:
    topic = topic_code(parsed)
    cycle_suffix = "di" if "日" in parsed.get("refresh_cycle", "") or "T+1" in parsed.get("refresh_cycle", "") else "df"
    return {
        "ods": f"ods_{topic}_event_di",
        "dwd": f"dwd_{topic}_detail_di",
        "dws": f"dws_{topic}_day_summary_{cycle_suffix}",
        "ads": f"ads_{topic}_report_{cycle_suffix}",
    }


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    header_line = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_line, separator, *body])
