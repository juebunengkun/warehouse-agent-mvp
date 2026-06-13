from __future__ import annotations


def test_sql_style_rejects_select_star():
    from dw_agent.nodes.review_sql_style import review_sql_style_text

    review = review_sql_style_text("INSERT OVERWRITE TABLE ads_x PARTITION (dt='${bizdate}') SELECT * FROM dws_x;")

    assert review["passed"] is False
    assert any(issue["rule"] == "NO_SELECT_STAR" for issue in review["issues"])


def test_sql_style_rejects_too_many_ctes():
    from dw_agent.nodes.review_sql_style import review_sql_style_text

    sql = """
WITH traffic AS (SELECT user_id FROM dwd_a),
orders AS (SELECT user_id FROM dwd_b),
payments AS (SELECT user_id FROM dwd_c),
refunds AS (SELECT user_id FROM dwd_d)
INSERT OVERWRITE TABLE ads_x PARTITION (dt='${bizdate}')
SELECT user_id FROM traffic;
"""
    review = review_sql_style_text(sql)

    assert review["passed"] is False
    assert any(issue["rule"] == "MAX_CTE_COUNT" for issue in review["issues"])


def test_sql_style_rejects_bad_cte_names():
    from dw_agent.nodes.review_sql_style import review_sql_style_text

    sql = """
WITH base AS (SELECT user_id FROM dwd_a),
tmp AS (SELECT user_id FROM base),
final AS (SELECT user_id FROM tmp)
INSERT OVERWRITE TABLE ads_x PARTITION (dt='${bizdate}')
SELECT user_id FROM final;
"""
    review = review_sql_style_text(sql)

    assert review["passed"] is False
    assert any(issue["rule"] == "BAD_CTE_NAME" for issue in review["issues"])


def test_sql_style_review_still_runs():
    from dw_agent.nodes.review_sql_style import review_sql_style_text

    sql = """
WITH traffic_events AS (SELECT user_id, channel_id FROM dwd_visit_di),
order_events AS (SELECT user_id, pay_amount FROM dwd_order_di),
payment_events AS (SELECT user_id, pay_amount FROM dwd_pay_di),
refund_events AS (SELECT user_id, refund_amount FROM dwd_refund_di)
INSERT OVERWRITE TABLE dws_bad PARTITION (dt='${bizdate}')
SELECT
  dwd.channel_id,
  SUM(dwd.pay_amount) / COUNT(dwd.user_id) AS arpu
FROM dwd_order_di dwd
LEFT JOIN dim_channel_df
  ON dwd.channel_id = dim_channel_df.channel_id
GROUP BY dwd.channel_id;
"""
    review = review_sql_style_text(sql)
    rules = {issue["rule"] for issue in review["issues"]}

    assert review["passed"] is False
    assert {"MAX_CTE_COUNT", "DIM_JOIN_REQUIRES_PARTITION", "DIVISION_REQUIRES_ZERO_GUARD"}.issubset(rules)
