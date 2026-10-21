-- Independent DuckDB recomputation for stage 2, straight from the raw CSVs.
-- Per (estimated week, customer state): A and L counts; per week: median purchase->delivery hours (A+L).
-- Window bounds are passed in; the bucket rule is restated here, not imported from Python.
WITH o AS (
    SELECT o.order_id, o.order_status,
           CAST(o.order_purchase_timestamp      AS TIMESTAMP) AS purchased_at,
           CAST(o.order_delivered_customer_date AS TIMESTAMP) AS delivered_at,
           CAST(o.order_estimated_delivery_date AS TIMESTAMP) AS estimated_at,
           COALESCE(c.customer_state, 'UNKNOWN')              AS state
    FROM read_csv($orders_csv, all_varchar = true) o
    LEFT JOIN read_csv($customers_csv, all_varchar = true) c USING (customer_id)
),
b AS (
    SELECT *, date_trunc('week', estimated_at) AS estimated_week,
           CASE
             WHEN estimated_at IS NULL OR CAST(estimated_at AS DATE) < CAST(purchased_at AS DATE) THEN 'NO_VALID_ESTIMATE'
             WHEN order_status IN ('canceled', 'unavailable') THEN 'X'
             WHEN order_status = 'delivered' AND delivered_at IS NOT NULL AND delivered_at >= purchased_at
                  AND CAST(delivered_at AS DATE) <= CAST(estimated_at AS DATE) THEN 'A'
             WHEN order_status = 'delivered' AND delivered_at IS NOT NULL AND delivered_at >= purchased_at THEN 'L'
             ELSE 'U'
           END AS bucket
    FROM o
),
w AS (SELECT * FROM b WHERE bucket <> 'NO_VALID_ESTIMATE'
        AND estimated_week BETWEEN CAST($first_week AS TIMESTAMP) AND CAST($last_week AS TIMESTAMP))
SELECT 'state' AS kind, estimated_week, state,
       SUM(CASE WHEN bucket = 'A' THEN 1 ELSE 0 END) AS a,
       SUM(CASE WHEN bucket = 'L' THEN 1 ELSE 0 END) AS l,
       NULL::DOUBLE AS cycle_hours_median
FROM w GROUP BY estimated_week, state
UNION ALL
SELECT 'week', estimated_week, NULL, NULL, NULL,
       median((epoch(delivered_at) - epoch(purchased_at)) / 3600.0)
FROM w WHERE bucket IN ('A', 'L') GROUP BY estimated_week
ORDER BY kind, estimated_week, state;
