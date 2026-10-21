# Stage 2 — Weekly Delivery Review, State Decomposition, Stage Timing

Public Olist data, independent offline analysis. Retrospective: estimated-delivery weeks 2017-02-27 → 2018-07-23 (74 weeks, approved window). Every number comes from `python -m olist_analytics.run_stage2`, which runs only on a READY stage-1 release and writes this file only after every check in §7 passes. Main KPI: **on-time rate among delivered orders with valid dates**, A/(A+L).

## 1. Weekly trend
- Window: 92.92% on-time over 84,129 eligible orders; U 1,563, X 1,037, outcome coverage 98.18%.
- Lowest week: 2018-03-26 at 74.6% (n=1,470). Highest: 2018-07-16 at 99.3% (n=2,266).
- Weekly outcome coverage ranges 95.5%–99.6%; the main KPI is always read next to it.
- Full weekly table: `outputs/stage2/weekly_kpis.csv` (cycle and stage hours each carry their own n).

## 2. Figure 04A — latest pair of weeks
**Question.** Which customer states contributed to the on-time change between estimated weeks 2018-07-16 and 2018-07-23?

- **Finding.** On-time fell 99.29% → 97.50% (-1.80 pts). Largest ranked contributors: SP -1.01 pts (OTD 99.4% → 96.7%, n 976→576); RS -0.23 pts (OTD 100.0% → 96.4%, n 137→110); RJ -0.18 pts (OTD 99.1% → 97.7%, n 218→260).
- **Evidence.** Performance terms sum to -1.91 pts; mix +0.12 pts; entry +0.00 pts; exit +0.00 pts. Eligible orders 2,266 → 1,678. All terms add up to the change exactly (identity checked).
- **Limitation.** Descriptive decomposition only: a state's performance term can still hide seller, category or route changes inside that state. States with fewer than 30 eligible orders in either week stay in the totals but are not ranked. The current week is the last one admitted by the 31-day horizon; with a 45- or 60-day horizon it would be excluded, so its on-time rate may still be biased upward by censoring.
- **Recommended check.** Look at SP orders that were late in the week of 2018-07-23: which sellers and stages they share (stage-timing view below).

| customer_state_reported | eligible_prior | eligible_current | otd_prior | otd_current | performance | mix | entry | exit | total |
|---|---|---|---|---|---|---|---|---|---|
| SP | 976 | 576 | 99.4% | 96.7% | -1.04 | +0.03 | +0.00 | +0.00 | -1.01 |
| RS | 137 | 110 | 100.0% | 96.4% | -0.23 | -0.00 | +0.00 | +0.00 | -0.23 |
| RJ | 218 | 260 | 99.1% | 97.7% | -0.17 | -0.00 | +0.00 | +0.00 | -0.18 |
| MG | 282 | 196 | 100.0% | 99.5% | -0.06 | -0.01 | +0.00 | +0.00 | -0.07 |
| ES | 46 | 37 | 100.0% | 97.3% | -0.06 | +0.00 | +0.00 | +0.00 | -0.06 |
| GO | 40 | 39 | 100.0% | 97.4% | -0.05 | +0.00 | +0.00 | +0.00 | -0.05 |
| SC | 87 | 76 | 100.0% | 98.7% | -0.06 | +0.01 | +0.00 | +0.00 | -0.05 |
| PE | 40 | 30 | 97.5% | 100.0% | +0.04 | +0.00 | +0.00 | +0.00 | +0.04 |
| other 15 states | 440 | 354 | n/a | n/a | -0.29 | +0.09 | +0.00 | +0.00 | -0.20 |

Rates in %; terms in percentage points. The last row aggregates every state not shown, so the column `total` sums to the overall change.

## 3. Largest weekly decline in the window
- **Finding.** 2018-03-12 → 2018-03-19: 85.75% → 76.17% (-9.58 pts). Ranked contributors: RJ -2.47 pts (OTD 62.6% → 45.8%, n 278→284); SP -2.12 pts (OTD 91.3% → 86.1%, n 869→787); MG -1.51 pts (OTD 91.1% → 78.3%, n 248→276).
- **Evidence.** Performance -9.27 pts, mix -0.34 pts, entry + exit +0.03 pts.
- **Limitation.** The decline is broad, not one state; the data cannot say why. Any external cause (weather, strikes, holidays) would need a separate source and is not claimed here.
- **Recommended check.** Compare that week's late orders by seller state and stage before naming a cause.

## 4. Performance vs mix across all weekly pairs
- 73 consecutive pairs. Mix + entry + exit outweighs performance in 10 of them.
- Median |performance| 1.01 pts vs median |mix + entry + exit| 0.21 pts.
- Reading: week-to-week swings in this window mostly come from on-time changes **within** states, not from orders shifting between states. This is a description of the window, not a forecast.

## 5. Stage-timing diagnosis (not responsibility)
Orders in the window that are OTD-eligible and stage-eligible: on time n=77,198, late n=5,934.

| stage | median on time (h) | median late (h) | P90 on time (h) | P90 late (h) |
|---|---|---|---|---|
| approval | 0.3 | 0.4 | 33.3 | 38.2 |
| handling | 44.2 | 72.5 | 137.7 | 332.3 |
| transit | 170.3 | 657.0 | 384.6 | 1087.9 |
| total | 244.6 | 776.1 | 483.2 | 1210.9 |

- **Finding.** Late orders are slower in both stages, and the gap is far larger in transit (median 657 h vs 170 h) than in seller handling (median 72 h vs 44 h).
- **Evidence.** Handed to the carrier after the seller's `shipping_limit_date`: 25.9% of late orders vs 7.7% of on-time orders.
- **Limitation.** Groups are selected using the delivery outcome relative to each order's estimate; the stage differences are descriptive, not estimates of what causes lateness. Medians of stages do not add up to the median total. The deadline used is the earliest `shipping_limit_date` among an order's items. This compares an order-level handoff with an item-level deadline, including multi-seller orders; it is a deadline proxy and cannot establish individual seller compliance. Transit has no comparable standard in the data. So this shows *where time is spent*, not *who caused the delay*. No 'share of delay caused by seller / carrier' is reported.
- **Recommended check.** In stage 3, test whether purchase-time signals (distance, seller history, estimated days) predict the long-transit cases; that is a prediction question, not attribution.

## 6. Weekly table
| estimated_week | eligible_orders | U | X | otd_rate | outcome_coverage | cycle_hours_median | cycle_hours_p90 |
|---|---|---|---|---|---|---|---|
| 2017-02-27 | 341 | 9 | 7 | 97.4% | 97.4% | 212.0 | 407.8 |
| 2017-03-06 | 428 | 20 | 19 | 97.0% | 95.5% | 227.3 | 456.0 |
| 2017-03-13 | 564 | 23 | 25 | 96.5% | 96.1% | 254.9 | 477.7 |
| 2017-03-20 | 760 | 30 | 19 | 97.5% | 96.2% | 268.9 | 478.3 |
| 2017-03-27 | 600 | 21 | 22 | 97.0% | 96.6% | 258.4 | 530.8 |
| 2017-04-03 | 624 | 16 | 9 | 95.8% | 97.5% | 246.2 | 512.7 |
| 2017-04-10 | 516 | 16 | 15 | 95.7% | 97.0% | 240.1 | 493.8 |
| 2017-04-17 | 466 | 14 | 11 | 94.0% | 97.1% | 247.4 | 498.9 |
| 2017-04-24 | 525 | 17 | 6 | 96.0% | 96.9% | 244.2 | 502.1 |
| 2017-05-01 | 439 | 10 | 7 | 94.1% | 97.8% | 241.8 | 574.2 |
| 2017-05-08 | 612 | 26 | 6 | 89.4% | 95.9% | 324.9 | 655.5 |
| 2017-05-15 | 577 | 10 | 8 | 91.3% | 98.3% | 328.0 | 627.5 |
| 2017-05-22 | 679 | 28 | 9 | 95.3% | 96.0% | 286.6 | 544.6 |
| 2017-05-29 | 991 | 26 | 16 | 97.1% | 97.4% | 241.7 | 455.7 |
| 2017-06-05 | 833 | 23 | 15 | 97.0% | 97.3% | 249.7 | 491.6 |
| 2017-06-12 | 648 | 15 | 9 | 97.7% | 97.7% | 234.2 | 448.5 |
| 2017-06-19 | 775 | 19 | 12 | 97.9% | 97.6% | 214.3 | 439.3 |
| 2017-06-26 | 847 | 21 | 15 | 97.8% | 97.6% | 253.5 | 457.1 |
| 2017-07-03 | 851 | 17 | 14 | 96.8% | 98.0% | 258.3 | 474.7 |
| 2017-07-10 | 749 | 16 | 11 | 96.4% | 97.9% | 261.0 | 488.8 |
| 2017-07-17 | 720 | 17 | 14 | 97.1% | 97.7% | 248.4 | 467.5 |
| 2017-07-24 | 734 | 23 | 14 | 97.7% | 97.0% | 237.5 | 455.3 |
| 2017-07-31 | 851 | 12 | 20 | 98.1% | 98.6% | 244.4 | 458.0 |
| 2017-08-07 | 939 | 17 | 21 | 97.0% | 98.2% | 245.3 | 463.6 |
| 2017-08-14 | 925 | 18 | 16 | 96.8% | 98.1% | 238.3 | 477.6 |
| 2017-08-21 | 920 | 9 | 11 | 97.1% | 99.0% | 228.4 | 482.6 |
| 2017-08-28 | 976 | 23 | 11 | 97.3% | 97.7% | 224.7 | 455.6 |
| 2017-09-04 | 787 | 14 | 10 | 97.2% | 98.3% | 233.1 | 457.7 |
| 2017-09-11 | 961 | 23 | 15 | 96.4% | 97.7% | 223.4 | 457.7 |
| 2017-09-18 | 1144 | 27 | 18 | 97.1% | 97.7% | 244.2 | 451.8 |
| 2017-09-25 | 1140 | 17 | 13 | 96.3% | 98.5% | 249.9 | 477.5 |
| 2017-10-02 | 1019 | 12 | 9 | 93.6% | 98.8% | 265.4 | 511.4 |
| 2017-10-09 | 599 | 11 | 9 | 94.3% | 98.2% | 272.2 | 539.2 |
| 2017-10-16 | 776 | 11 | 13 | 96.8% | 98.6% | 237.0 | 491.9 |
| 2017-10-23 | 1102 | 34 | 19 | 96.8% | 97.0% | 229.0 | 458.3 |
| 2017-10-30 | 1095 | 13 | 19 | 96.3% | 98.8% | 244.6 | 473.3 |
| 2017-11-06 | 1325 | 17 | 37 | 95.3% | 98.7% | 247.7 | 482.2 |
| 2017-11-13 | 917 | 19 | 13 | 95.9% | 98.0% | 257.2 | 496.9 |
| 2017-11-20 | 761 | 13 | 19 | 95.4% | 98.3% | 266.6 | 510.4 |
| 2017-11-27 | 1252 | 21 | 35 | 95.0% | 98.4% | 249.2 | 487.2 |
| 2017-12-04 | 1400 | 33 | 29 | 94.1% | 97.7% | 272.5 | 476.5 |
| 2017-12-11 | 1783 | 32 | 21 | 86.2% | 98.2% | 295.0 | 622.9 |
| 2017-12-18 | 2162 | 38 | 24 | 81.9% | 98.3% | 343.7 | 762.8 |
| 2017-12-25 | 1430 | 32 | 14 | 88.5% | 97.8% | 319.0 | 727.0 |
| 2018-01-01 | 1226 | 19 | 15 | 87.4% | 98.5% | 324.2 | 810.1 |
| 2018-01-08 | 1288 | 26 | 11 | 92.1% | 98.0% | 339.6 | 721.0 |
| 2018-01-15 | 1143 | 13 | 7 | 95.5% | 98.9% | 315.9 | 644.3 |
| 2018-01-22 | 953 | 15 | 8 | 95.6% | 98.5% | 268.5 | 606.0 |
| 2018-01-29 | 1512 | 33 | 14 | 96.2% | 97.9% | 254.2 | 539.5 |
| 2018-02-05 | 2112 | 46 | 15 | 95.3% | 97.9% | 273.0 | 565.8 |
| 2018-02-12 | 1198 | 18 | 10 | 93.5% | 98.5% | 288.9 | 631.3 |
| 2018-02-19 | 1807 | 22 | 37 | 92.0% | 98.8% | 297.3 | 628.7 |
| 2018-02-26 | 1109 | 10 | 18 | 94.8% | 99.1% | 309.7 | 604.0 |
| 2018-03-05 | 2062 | 18 | 40 | 90.5% | 99.1% | 335.3 | 671.2 |
| 2018-03-12 | 2189 | 24 | 47 | 85.7% | 98.9% | 341.0 | 735.6 |
| 2018-03-19 | 2081 | 34 | 19 | 76.2% | 98.4% | 370.4 | 872.0 |
| 2018-03-26 | 1470 | 17 | 4 | 74.6% | 98.9% | 373.9 | 858.1 |
| 2018-04-02 | 1664 | 42 | 7 | 79.2% | 97.5% | 321.7 | 793.2 |
| 2018-04-09 | 1737 | 43 | 9 | 84.5% | 97.6% | 302.9 | 731.9 |
| 2018-04-16 | 1544 | 44 | 4 | 87.9% | 97.2% | 301.7 | 691.6 |
| 2018-04-23 | 1365 | 28 | 7 | 91.1% | 98.0% | 259.4 | 629.1 |
| 2018-04-30 | 1077 | 25 | 3 | 94.2% | 97.7% | 222.3 | 584.7 |
| 2018-05-07 | 1590 | 23 | 8 | 96.7% | 98.6% | 218.1 | 524.3 |
| 2018-05-14 | 1884 | 32 | 9 | 96.4% | 98.3% | 203.9 | 481.0 |
| 2018-05-21 | 2095 | 35 | 6 | 96.2% | 98.4% | 204.3 | 459.3 |
| 2018-05-28 | 1912 | 26 | 16 | 91.6% | 98.7% | 211.2 | 504.3 |
| 2018-06-04 | 1796 | 39 | 9 | 87.2% | 97.9% | 295.3 | 613.7 |
| 2018-06-11 | 715 | 3 | 1 | 97.8% | 99.6% | 353.7 | 542.3 |
| 2018-06-18 | 628 | 5 | 3 | 98.2% | 99.2% | 235.0 | 505.4 |
| 2018-06-25 | 987 | 11 | 2 | 99.1% | 98.9% | 132.0 | 356.8 |
| 2018-07-02 | 1140 | 8 | 5 | 98.3% | 99.3% | 172.6 | 384.8 |
| 2018-07-09 | 1358 | 6 | 6 | 98.9% | 99.6% | 199.7 | 404.6 |
| 2018-07-16 | 2266 | 17 | 4 | 99.3% | 99.3% | 194.4 | 405.3 |
| 2018-07-23 | 1678 | 18 | 14 | 97.5% | 98.9% | 195.8 | 391.4 |

## 7. Blocking checks
| check | expected | actual | pass |
|---|---|---|---|
| window weeks used == approved selection | 2017-02-27..2018-07-23 (74) | 2017-02-27..2018-07-23 (74) | True |
| window A / L / U / X == stage-1 selection | 78176/5953/1563/1037 | 78176/5953/1563/1037 | True |
| state eligible totals == weekly eligible (every week) | 74 | 74 | True |
| decomposition identity holds for every comparable pair (max &#124;gap&#124; < 1e-12) | True | True | True |
| SQL state x week A/L cells matching | 1817 | 1817 | True |
| SQL weekly median cycle hours (max &#124;diff&#124; < 1e-6 h) | True | True | True |
| SQL stage timing n, median, P90 and mean (all outcome-stage cells) | 8 | 8 | True |

## 8. Limits that apply to every number above
- Retrospective window inside an inferred observation boundary; late cohorts near the end may be censored (stage-1 report §9, sensitivity table).
- The KPI covers delivered orders with valid dates only; U and X are reported next to it, never folded in.
- Estimated delivery date is Olist's estimate shown to the customer, not a contractual SLA.
- Olist has no carrier IDs; customer state is the grouping, and sellers are not carriers.

## 9. Seller-associated orders to inspect

Single-seller orders only, across the entire 74-week window. Minimum 30 OTD-eligible orders; all sellers remain in the exported queue with a threshold flag. These are investigation candidates, not causal responsibility rankings. 95% Wilson intervals capture binomial sampling uncertainty only; routes, categories, promises, clustering and censoring are not adjusted.

| seller_label | seller_state | eligible_orders | L | U | otd_rate | otd_wilson_low | otd_wilson_high | stage_n | handling_median_h | transit_median_h |
|---|---|---|---|---|---|---|---|---|---|---|
| Seller 1770 | SP | 33 | 12 | 5 | 63.6% | 46.6% | 77.8% | 33 | 212.1 | 283.3 |
| Seller 0875 | PR | 65 | 22 | 4 | 66.2% | 54.0% | 76.5% | 64 | 176.3 | 222.3 |
| Seller 2430 | SP | 43 | 14 | 2 | 67.4% | 52.5% | 79.5% | 43 | 77.9 | 317.7 |
| Seller 0420 | MG | 40 | 12 | 3 | 70.0% | 54.6% | 81.9% | 40 | 95.1 | 214.0 |
| Seller 1365 | SP | 40 | 11 | 1 | 72.5% | 57.2% | 83.9% | 40 | 220.7 | 183.0 |
| Seller 2442 | SC | 33 | 8 | 0 | 75.8% | 59.0% | 87.2% | 33 | 38.7 | 336.0 |
| Seller 1411 | PR | 162 | 38 | 1 | 76.5% | 69.5% | 82.4% | 162 | 167.2 | 191.1 |
| Seller 1695 | SP | 93 | 21 | 2 | 77.4% | 67.9% | 84.7% | 93 | 149.6 | 188.5 |
| Seller 1801 | SP | 36 | 8 | 2 | 77.8% | 61.9% | 88.3% | 36 | 50.7 | 335.5 |
| Seller 2393 | SP | 43 | 9 | 0 | 79.1% | 64.8% | 88.6% | 41 | 53.0 | 157.9 |

Full identifiers and counts: `outputs/stage2/seller_review_queue.csv`. The page uses stable aliases; no review of these candidates has yet been recorded.
