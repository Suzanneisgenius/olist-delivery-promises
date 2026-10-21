# Source-to-Target Mapping — `orders_mart` (one row per `order_id`)

| Target column(s) | Source | Rule |
|---|---|---|
| order_id, order_status, timestamps | orders | as is (parsed as naive local time) |
| customer_unique_id, customer_zip_code_prefix, customer_state | customers | many-to-one on customer_id |
| n_item_lines, n_distinct_products, n_sellers, n_categories | order_items + products | aggregated per order_id before joining; lines keyed by order_id + order_item_id |
| items_price_sum, items_freight_sum | order_items | sum per order; conservation checked against raw totals |
| weight_g_sum, weight_missing_lines | order_items + products | sum of known weights; missing count kept (no fill) |
| top_price_category | order_items + products | category of the highest-price line (ties: lowest order_item_id) |
| single_seller_id, seller_state, seller_zip_code_prefix | order_items + sellers | only when the order has exactly one seller; else null |
| n_payments, payment_value_sum | order_payments | aggregated per order (QA only) |
| cust_lat/lng, seller_lat/lng, *_geo_dispersed | geolocation | per zip prefix: median of in-Brazil points; dispersion flag at p95 deviation > 50 km |
| distance_km | derived | haversine between the two prefix medians; proxy, not route distance; null if multi-seller or geo missing |
| estimated_week, outcome_bucket, is_late, days_late | derived | see metric dictionary |
| approval/handling/transit/total_hours | derived | timestamp differences in hours; anomalies flagged, not dropped |
| n_reviews, review_*_primary, review_score_latest | order_reviews | primary = first answered on/after delivery; latest kept for sensitivity |
| reason_codes | derived | ";"-joined codes; long form in outputs/qa/order_reason_codes.csv |
| is_*_eligible | derived | per-use flags |
