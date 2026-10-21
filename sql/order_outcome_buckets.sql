-- Independent DuckDB re-implementation of outcome buckets, read straight from the raw CSV.
-- Used to cross-check the pandas orders_mart (counts per estimated week and bucket).
WITH o AS (
    SELECT
        order_id,
        order_status,
        CAST(order_purchase_timestamp      AS TIMESTAMP) AS purchased_at,
        CAST(order_delivered_customer_date AS TIMESTAMP) AS delivered_at,
        CAST(order_estimated_delivery_date AS TIMESTAMP) AS estimated_at
    FROM read_csv($orders_csv, all_varchar = true)
),
b AS (
    SELECT
        order_id,
        CASE WHEN estimated_at IS NULL OR CAST(estimated_at AS DATE) < CAST(purchased_at AS DATE)
             THEN NULL ELSE date_trunc('week', estimated_at) END AS estimated_week,
        CASE
            WHEN estimated_at IS NULL
              OR CAST(estimated_at AS DATE) < CAST(purchased_at AS DATE) THEN 'NO_VALID_ESTIMATE'
            WHEN order_status IN ('canceled', 'unavailable')         THEN 'X'
            WHEN order_status = 'delivered' AND delivered_at IS NOT NULL
                 AND delivered_at >= purchased_at
                 AND CAST(delivered_at AS DATE) <= CAST(estimated_at AS DATE) THEN 'A'
            WHEN order_status = 'delivered' AND delivered_at IS NOT NULL
                 AND delivered_at >= purchased_at                    THEN 'L'
            ELSE 'U'
        END AS outcome_bucket
    FROM o
)
SELECT estimated_week, outcome_bucket, COUNT(*) AS orders
FROM b
GROUP BY ALL
ORDER BY estimated_week, outcome_bucket;
