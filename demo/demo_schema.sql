CREATE SCHEMA IF NOT EXISTS main;

CREATE OR REPLACE TABLE dim_channel_df (
  channel_id VARCHAR,
  channel_name VARCHAR,
  channel_type VARCHAR,
  dt DATE
);

CREATE OR REPLACE TABLE dim_region_df (
  region_id VARCHAR,
  province_name VARCHAR,
  city_name VARCHAR,
  dt DATE
);

CREATE OR REPLACE TABLE dim_user_profile_df (
  user_id VARCHAR,
  user_type VARCHAR,
  member_level VARCHAR,
  dt DATE
);

CREATE OR REPLACE TABLE dim_category_df (
  category_id VARCHAR,
  category_level1_name VARCHAR,
  category_level2_name VARCHAR,
  dt DATE
);

CREATE OR REPLACE TABLE dwd_sales_detail_di (
  order_id VARCHAR,
  user_id VARCHAR,
  sku_id VARCHAR,
  category_id VARCHAR,
  channel_id VARCHAR,
  region_id VARCHAR,
  pay_amount DECIMAL(18, 2),
  refund_amount DECIMAL(18, 2),
  order_status VARCHAR,
  pay_time TIMESTAMP,
  refund_time TIMESTAMP,
  dt DATE
);

CREATE OR REPLACE TABLE dwd_user_behavior_event_di (
  event_id VARCHAR,
  user_id VARCHAR,
  sku_id VARCHAR,
  category_id VARCHAR,
  channel_id VARCHAR,
  event_type VARCHAR,
  event_time TIMESTAMP,
  dt DATE
);

CREATE OR REPLACE TABLE dws_category_channel_day_summary_di (
  stat_date DATE,
  category_id VARCHAR,
  category_level1_name VARCHAR,
  category_level2_name VARCHAR,
  channel_id VARCHAR,
  channel_name VARCHAR,
  channel_type VARCHAR,
  user_type VARCHAR,
  member_level VARCHAR,
  visit_user_cnt BIGINT,
  exposure_cnt BIGINT,
  click_cnt BIGINT,
  cart_user_cnt BIGINT,
  order_user_cnt BIGINT,
  pay_user_cnt BIGINT,
  pay_order_cnt BIGINT,
  pay_amount DECIMAL(18, 2),
  refund_order_cnt BIGINT,
  refund_amount DECIMAL(18, 2),
  dt DATE
);

CREATE OR REPLACE TABLE ads_category_operation_daily_report_di (
  stat_date DATE,
  category_level1_name VARCHAR,
  category_level2_name VARCHAR,
  channel_name VARCHAR,
  channel_type VARCHAR,
  user_type VARCHAR,
  member_level VARCHAR,
  visit_user_cnt BIGINT,
  exposure_cnt BIGINT,
  click_cnt BIGINT,
  cart_user_cnt BIGINT,
  order_user_cnt BIGINT,
  pay_user_cnt BIGINT,
  pay_order_cnt BIGINT,
  pay_amount DECIMAL(18, 2),
  refund_order_cnt BIGINT,
  refund_amount DECIMAL(18, 2),
  click_rate DECIMAL(18, 6),
  cart_rate DECIMAL(18, 6),
  pay_rate DECIMAL(18, 6),
  avg_order_amount DECIMAL(18, 2),
  refund_rate DECIMAL(18, 6),
  dt DATE
);
