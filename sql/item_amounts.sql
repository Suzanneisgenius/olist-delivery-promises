-- Independent totals from raw order_items (lines, price, freight) for the amount-conservation check.
SELECT COUNT(*)                         AS item_lines,
       COUNT(DISTINCT order_id)         AS orders_with_items,
       SUM(CAST(price AS DOUBLE))       AS price_sum,
       SUM(CAST(freight_value AS DOUBLE)) AS freight_sum
FROM read_csv($items_csv, all_varchar = true);
