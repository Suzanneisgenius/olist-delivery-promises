# Stage 1 — Data Audit and Order Mart (rev. 1.1)

Public Olist data, independent offline analysis. Every number below comes from this run (`python -m olist_analytics.run_stage1`) on the files fingerprinted in §1. This report is written only after every blocking check in §3 passes.

## 1. Source manifest
Source: Olist Brazilian E-Commerce Public Dataset (Kaggle: olistbr/brazilian-ecommerce). Obtained: archive.zip uploaded by project owner on 2026-10-11; Kaggle version number not recorded in the archive. Data license: CC BY-NC-SA 4.0 (per Kaggle page; record again at download). `records` is the CSV record count; `physical_lines` differs for reviews because comments contain line breaks. Loaded source tables keep `source_record_no` (1-based record number, not a physical line number); the mart traces back by `order_id`.

| table | file | records | physical_lines | columns | sha256 |
|---|---|---|---|---|---|
| orders | olist_orders_dataset.csv | 99441 | 99441 | 8 | 8df58ef3d2d7e994… |
| order_items | olist_order_items_dataset.csv | 112650 | 112650 | 7 | 0bc4d068c4fe38cb… |
| order_payments | olist_order_payments_dataset.csv | 103886 | 103886 | 5 | 4f713964f2815dbb… |
| order_reviews | olist_order_reviews_dataset.csv | 99224 | 104719 | 7 | 012b61c7593e34f5… |
| customers | olist_customers_dataset.csv | 99441 | 99441 | 5 | 983a422239e1712d… |
| sellers | olist_sellers_dataset.csv | 3095 | 3095 | 4 | 1f643d2b950373b8… |
| products | olist_products_dataset.csv | 32951 | 32951 | 9 | 3e6569628a17fbc7… |
| geolocation | olist_geolocation_dataset.csv | 1000163 | 1000163 | 5 | b514f6fc991b9566… |
| category_translation | product_category_name_translation.csv | 71 | 71 | 2 | a81f0d1f27b27e72… |

Environment: Python 3.13.16, pandas 3.0.5, numpy 2.5.3, DuckDB 1.5.6, PyYAML 6.0.3.

## 2. Data contract
73 checks: PASS 73. Hard checks (keys, allowed values, zip format, parsing) pass. Foreign keys include orders.customer_id → customers.customer_id; an order without a customer record is kept and reported under state `UNKNOWN`.

## 3. Blocking checks (release gate)
Each row must pass, or the run writes `qa/RELEASE_BLOCKED.json`, deletes any previous report, and exits non-zero.

| check | expected | actual | pass |
|---|---|---|---|
| orders_mart rows == orders rows | 99441.0 | 99441.0 | True |
| orders_mart order_id unique | 1.0 | 1.0 | True |
| item lines carried into mart | 112650.0 | 112650.0 | True |
| price sum conserved (BRL, rounded) | 13591643.7 | 13591643.7 | True |
| freight sum conserved (BRL, rounded) | 2251909.54 | 2251909.54 | True |
| payment sum conserved (BRL, rounded) | 16008872.12 | 16008872.12 | True |
| stage identity: total = approval + handling + transit (max abs gap, h, stage-eligible) | 0.0 | 0.0 | True |
| SQL item lines (raw CSV) | 112650.0 | 112650.0 | True |
| SQL price sum (raw CSV) | 13591643.7 | 13591643.7 | True |
| SQL outcome buckets: week x bucket cells matching | 373.0 | 373.0 | True |
| weekly table orders + unassigned == mart rows | 99441.0 | 99441.0 | True |
| OTD-eligible orders by state (incl. UNKNOWN) == all OTD-eligible | 96470.0 | 96470.0 | True |
| independent csv-module re-check of sample (bucket, days late) | 20.0 | 20.0 | True |

## 4. Outcome buckets (mutually exclusive, all orders)
A = delivered on/before the estimated day · L = delivered after · U = outcome unconfirmed · X = canceled/unavailable · NO_VALID_ESTIMATE = estimated date missing or earlier than purchase (never assigned to a week; 0 orders in this file).

| outcome_bucket | orders |
|---|---|
| A | 89936 |
| L | 6534 |
| U | 1737 |
| X | 1234 |

## 5. Reason codes (overlap allowed; orders per code, not additive)
| reason_code | orders | affects |
|---|---|---|
| no_review_after_delivery | 5299 | review |
| carrier_before_approved | 1359 | stage |
| multi_seller | 1278 | model |
| no_items | 775 | model |
| dispersed_geo_prefix | 634 | distance (flag only) |
| missing_customer_geo | 279 | distance |
| payment_mismatch | 250 | info |
| missing_seller_geo | 216 | distance |
| carrier_before_purchase | 166 | stage |
| delivered_before_carrier | 23 | stage |
| missing_product_weight | 16 | weight (flag only) |
| missing_approved_at | 14 | stage |
| delivered_missing_date | 8 | otd,stage |
| canceled_with_delivery_date | 6 | otd |
| missing_carrier_date | 2 | stage |
| no_payment | 1 | info |

`carrier_before_approved` (1,359 orders) by bucket: A 1,326, L 24, U 9. Stage anomalies do not remove the 1,350 orders that already meet the OTD rule; the others are not OTD-eligible for unrelated reasons.

## 6. Eligibility by use
| flag | orders | share_of_all_orders |
|---|---|---|
| is_otd_eligible | 96470 | 0.9701 |
| is_stage_eligible | 95082 | 0.9562 |
| is_model_eligible_prelim | 95195 | 0.9573 |
| is_review_eligible | 91171 | 0.9168 |

Model eligibility is preliminary (single seller + confirmed outcome). Feature-availability rules come in stage 3.

## 7. Previously quoted numbers, recomputed
- Late share among delivered orders with valid dates, L/(A+L), all weeks: **6.77%** of 96,470 orders.
- Delivered orders with a negative handling or transit duration: **1,373**. Definition: status delivered AND (carrier_date < approved_at OR delivered_date < carrier_date). This does not cover every possible timestamp anomaly (see §5).

## 8. Geolocation and reviews
- Geolocation: 1,000,163 points; 31 fall outside the configured bounding box (a rectangle, not a national border) and are excluded from medians; 19,011 prefixes; 244 flagged as dispersed (p95 deviation > 50 km; kept).
- Reviews: 99,224 records; review_id repeats on 1,603 records (key is review_id + order_id); 547 orders have >1 review; 91,171 orders have a primary review (first answered on/after delivery); primary and latest score differ on 128 orders.

## 9. Comparison window
- Late activity drops sharply. An activity rule gives a conservative **inferred observation boundary of 2018-09-03**; it is not a confirmed extraction date (37 deliveries still appear after it; last timestamp 2018-10-17 17:30:18). Cohorts estimated near the end may be right-censored or selected, so they are left out of the main comparison.
- Horizon = 31 days: the ceiling of p95 of *observed* days late. It is itself affected by censoring and does not guarantee that 95% of unknown late orders were observed.
- Rule: A+L >= 200 per week; outcome coverage >= 95%; week end + horizon (ceil of p95 of observed days late) <= inferred observation boundary; longest consecutive run on a complete weekly calendar.
- **Selected window: estimated weeks 2017-02-27 → 2018-07-23 (74 weeks)** — A 78,176 · L 5,953 · U 1,563 · X 1,037.
  - On-time rate among delivered orders with valid dates: **92.92%**.
  - Outcome coverage (A+L)/(A+L+U): 98.18% — overall only; state/week levels are reported separately.
  - Auxiliary confirmed on-time share A/(A+L+U): 91.23% — does not replace the KPI.
- Weeks passing all weekly guards: 74; the selected window is the longest consecutive run (74 weeks). All summaries use `in_selected_window`.
- 96.6% of U orders in the window have an estimated date more than 60 days before the inferred boundary and a status of shipped / processing / invoiced. They are long-unconfirmed; the static data cannot tell why (not updated, lost, canceled without a record, or not delivered).
- With a 98% coverage guard, 39 weeks pass but the longest consecutive run is 7 weeks. 95% is a transparent policy choice that keeps a long comparison period; 98% is not statistically wrong.

### Window sensitivity — different windows, not confidence intervals
| horizon_days | min_coverage | weeks_passing_guards | selected_weeks | first_week | last_week | otd_rate | is_default |
|---|---|---|---|---|---|---|---|
| 31 | 0.95 | 74 | 74 | 2017-02-27 | 2018-07-23 | 92.92% | True |
| 31 | 0.98 | 39 | 7 | 2018-02-12 | 2018-03-26 | 86.09% | False |
| 45 | 0.95 | 72 | 72 | 2017-02-27 | 2018-07-09 | 92.65% | False |
| 45 | 0.98 | 37 | 7 | 2018-02-12 | 2018-03-26 | 86.09% | False |
| 60 | 0.95 | 70 | 70 | 2017-02-27 | 2018-06-25 | 92.46% | False |
| 60 | 0.98 | 35 | 7 | 2018-02-12 | 2018-03-26 | 86.09% | False |

Differences also reflect a different mix of weeks; they are not a bias correction.

## 10. Manual check
`outputs/qa/manual_check_sample.csv` lists 20 orders covering the listed typical cases (boundary rules are covered by unit tests). A scripted re-check that reads the raw orders CSV with the standard `csv` module agrees on bucket and days late for 20 of 20. This is a program check, not a human sign-off: `reviewer_ok` / `reviewer_note` stay empty for the person reviewing.

## 11. Readiness
- Data audit: **PASS** (every blocking check in §3 passed).
- Comparison readiness: **READY** — Computed window matches the window on record in config/approvals.yaml.
- Owner decision on record (2026-10-12, approved with conditions); conditions:
  1. retrospective comparison window; keep the censoring note and the 31/45/60-day sensitivity table
  2. main KPI name keeps 'delivered orders with valid dates': A/(A+L), shown with U, coverage, X, eligible denominator
  3. stage-timing anomalies affect stage analysis only, never OTD eligibility
  4. state decomposition follows docs/metric_dictionary.md exactly
- State decomposition (stage 2) follows `docs/metric_dictionary.md`: performance = w̄ × Δp; mix, entry and exit are measured against the common centre c = (P0+P1)/2. The overall identity holds; the mix term alone does not have a fixed total when states enter or exit.

