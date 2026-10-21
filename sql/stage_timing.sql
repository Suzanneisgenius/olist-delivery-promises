-- Independent stage eligibility and distributions, from raw orders (no mart import).
WITH o AS (
 SELECT order_status,
  CAST(order_purchase_timestamp AS TIMESTAMP) p,
  CAST(order_approved_at AS TIMESTAMP) a,
  CAST(order_delivered_carrier_date AS TIMESTAMP) c,
  CAST(order_delivered_customer_date AS TIMESTAMP) d,
  CAST(order_estimated_delivery_date AS TIMESTAMP) e
 FROM read_csv($orders_csv, all_varchar=true)
), eligible AS (
 SELECT CASE WHEN CAST(d AS DATE)<=CAST(e AS DATE) THEN 'on time (A)' ELSE 'late (L)' END AS outcome,
  (epoch(a)-epoch(p))/3600 approval,
  (epoch(c)-epoch(a))/3600 handling,
  (epoch(d)-epoch(c))/3600 transit,
  (epoch(d)-epoch(p))/3600 total
 FROM o WHERE order_status='delivered' AND p<=a AND a<=c AND c<=d
 AND CAST(e AS DATE)>=CAST(p AS DATE)
 AND date_trunc('week', e) BETWEEN CAST($first_week AS TIMESTAMP) AND CAST($last_week AS TIMESTAMP)
), long AS (
 SELECT outcome AS "group", 'approval' stage, approval AS duration_h FROM eligible UNION ALL
 SELECT outcome, 'handling', handling FROM eligible UNION ALL
 SELECT outcome, 'transit', transit FROM eligible UNION ALL
 SELECT outcome, 'total', total FROM eligible
)
SELECT "group", stage, COUNT(*) AS n, median(duration_h) median_h,
 quantile_cont(duration_h,0.9) p90_h, avg(duration_h) mean_h
FROM long GROUP BY "group", stage ORDER BY "group", stage;
