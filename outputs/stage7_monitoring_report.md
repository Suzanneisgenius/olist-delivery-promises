# Stage 7 — Monitoring a Frozen Promised-Date Policy (part 3)

> Exploratory extension. Rules registered in `config/date_policy.yaml` (`monitoring`); readings M1–M8 and deviation D1 in `docs/DATE_POLICY_DECISIONS.md`. Alarms trigger human review only — no automatic recalibration. Monitored policy: B0 (per-state quantile) at target 0.90, the policy parts 1–2 kept.

> **The registered 52-week in-control ARL is unattainable** with 1,200 orders/week, so h = 0 is used. At h = 0 the CUSUM never carries evidence across weeks: it is a **single-week log-likelihood-ratio rule**. Its exact in-control burden differs from the threshold rule's by many orders of magnitude, so the simulation below does **not** show that one method is better than the other.

## Exact in-control burden (independent binomial weeks, 1,200 orders)

The crossing probability is for one week. For the threshold rule it is NOT the rule's weekly alarm probability: an alarm needs two consecutive crossings, and its long-run alarm frequency is 1 / ARL.

| series | rule | one-week crossing prob. | full alarm condition | exact ARL (weeks) | assumption |
|---|---|---|---|---|---|
| B0_0.90 | single-week LLR (CUSUM at h=0) | 0.003827 | this week >= 149 misses of 1,200 | 261.3 | independent binomial weeks at p0; memoryless, so ARL = 1/q |
| B0_0.90 | threshold (2 consecutive low weeks, reset) | 2.209e-08 | 2 consecutive weeks each >= 181 misses of 1,200 | 2.0487e+15 | independent binomial weeks at p0; ARL = (1+q)/q^2, q = one-week crossing prob. |
| Olist_matched | single-week LLR (CUSUM at h=0) | 0.003113 | this week >= 133 misses of 1,200 | 321.206 | independent binomial weeks at p0; memoryless, so ARL = 1/q |
| Olist_matched | threshold (2 consecutive low weeks, reset) | 6.634e-09 | 2 consecutive weeks each >= 165 misses of 1,200 | 2.2724e+16 | independent binomial weeks at p0; ARL = (1+q)/q^2, q = one-week crossing prob. |

## h calibration by simulation (restricted mean: runs without an alarm by the cap count as cap + 1)

| series | h | restricted_mean_run_length_weeks | cap_weeks | runs | censored_runs | censored_share |
|---|---|---|---|---|---|---|
| B0_0.90 | 0.0 | 252.4248 | 1000.0 | 10000.0 | 210.0 | 0.021 |
| Olist_matched | 0.0 | 312.0789 | 1000.0 | 10000.0 | 453.0 | 0.0453 |

B0 coverage on evaluation orders: 93.95% (target 90%). Olist matched target: 91.26%.

## Simulation (500 replications × 30 weeks × 1,200 orders; order bootstrap)

Calendar delay = days from the change start (Monday) to the date the alarm week is final (its Sunday + longest promise + 1 day).

| design | scenario | rule | change_week | mean_coverage | mean_coverage_after_change | false_alarms_per_year | detected_share | missed_detection_share | median_delay_weeks | median_delay_days_to_final |
|---|---|---|---|---|---|---|---|---|---|---|
| order bootstrap (registered) | none | single_week_llr (CUSUM at h=0) |  | 0.94 |  | 0.0 |  |  |  |  |
| order bootstrap (registered) | none | threshold |  | 0.94 |  | 0.0 |  |  |  |  |
| order bootstrap (registered) | sudden | single_week_llr (CUSUM at h=0) | 9.0 | 0.901 | 0.887 | 0.0 | 0.926 | 0.074 | 5.0 | 77.0 |
| order bootstrap (registered) | sudden | threshold | 9.0 | 0.901 | 0.887 | 0.0 | 0.0 | 1.0 |  |  |
| order bootstrap (registered) | gradual | single_week_llr (CUSUM at h=0) | 5.0 | 0.874 | 0.864 | 0.0 | 1.0 | 0.0 | 10.0 | 112.0 |
| order bootstrap (registered) | gradual | threshold | 5.0 | 0.874 | 0.864 | 0.0 | 1.0 | 0.0 | 17.0 | 161.0 |
| order bootstrap (registered) | transient | single_week_llr (CUSUM at h=0) | 9.0 | 0.934 | 0.932 | 0.0 | 1.0 | 0.0 | 0.0 | 42.0 |
| order bootstrap (registered) | transient | threshold | 9.0 | 0.934 | 0.932 | 0.0 | 0.098 | 0.902 | 1.0 | 49.0 |
| week-resampled (exploratory) | none | single_week_llr (CUSUM at h=0) |  | 0.943 |  | 3.63 |  |  |  |  |
| week-resampled (exploratory) | none | threshold |  | 0.943 |  | 0.024 |  |  |  |  |

## Over-dispersion (exploratory)

Observed week-to-week variance of coverage ÷ binomial variance (1 = order-level noise only): B0_0.90_evaluation = 22.4, Olist_full_period = 34.2

## Historical replay — weeks with an alarm

Computed per purchase week, then labelled with `final_at`; weeks are not re-ordered by information arrival. This is harmless for the memoryless h = 0 rule but would matter for any rule with state.

| series | week | orders | coverage | cusum | cusum_alarm | threshold_alarm | final_at |
|---|---|---|---|---|---|---|---|
| B0_0.90 | 2018-05-14 00:00:00 | 1773 | 85.1 | 21.25 | True | False | 2018-06-25 00:00:00 |
| Olist_matched | 2018-05-14 00:00:00 | 1773 | 87.7 | 11.0 | True | False | 2018-07-19 00:00:00 |
| Olist_matched_full_period | 2017-11-20 00:00:00 | 2882 | 82.6 | 92.49 | True | False | 2018-01-26 00:00:00 |
| Olist_matched_full_period | 2017-11-27 00:00:00 | 2021 | 85.3 | 37.22 | True | True | 2018-01-29 00:00:00 |
| Olist_matched_full_period | 2018-02-12 00:00:00 | 1582 | 87.0 | 15.15 | True | False | 2018-04-23 00:00:00 |
| Olist_matched_full_period | 2018-02-19 00:00:00 | 1701 | 80.8 | 70.01 | True | False | 2018-05-03 00:00:00 |
| Olist_matched_full_period | 2018-02-26 00:00:00 | 1832 | 73.5 | 143.52 | True | True | 2018-05-12 00:00:00 |
| Olist_matched_full_period | 2018-03-05 00:00:00 | 1583 | 75.1 | 111.25 | True | False | 2018-05-13 00:00:00 |
| Olist_matched_full_period | 2018-03-12 00:00:00 | 1528 | 78.7 | 79.25 | True | True | 2018-05-21 00:00:00 |
| Olist_matched_full_period | 2018-03-19 00:00:00 | 1641 | 88.0 | 7.76 | True | False | 2018-05-20 00:00:00 |
| Olist_matched_full_period | 2018-03-26 00:00:00 | 1403 | 88.7 | 1.84 | True | False | 2018-05-26 00:00:00 |
| Olist_matched_full_period | 2018-05-14 00:00:00 | 1773 | 87.7 | 11.0 | True | False | 2018-07-19 00:00:00 |

## Blocking checks

| check | expected | actual | pass |
|---|---|---|---|
| config matches the registered SHA-256 | 9c1ff876fb1777719a95cdb606b1f78be7989441b328a7b664dc8076a95b4747 | 9c1ff876fb1777719a95cdb606b1f78be7989441b328a7b664dc8076a95b4747 | True |
| parts 1-2 report is current | True | True | True |
| parts 1-2 kept the simple state rule (B0) at target 0.90 | True | True | True |
| B0 rebuilt here reproduces parts 1-2 coverage | True | True | True |
| weekly replay counts every evaluation order once | 19950 | 19950 | True |
| h is the attainable value (h >= 0) closest to an in-control ARL of 52 weeks | True | True | True |
| h = 0: simulated restricted mean agrees with the exact geometric ARL (within 10%, given censoring) | True | True | True |
| 'none' scenario keeps the evaluation coverage (bootstrap sanity, +/- 0.5 pt) | True | True | True |
| each scenario has replications x weeks simulated weeks | True | True | True |
