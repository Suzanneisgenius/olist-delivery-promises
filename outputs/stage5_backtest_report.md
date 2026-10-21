# Stage 5 — Monthly Rolling-Origin Backtest

> **Retrospective stability study, not a new test.** All three evaluation months lie inside the stage-3 test period, which was inspected in v0.3.0 and v0.3.1. Hyperparameters are the frozen stage-3 choice (selected with labels known before 2018-04-01); nothing is tuned per fold.

## Protocol

- Cut-offs T: 2018-04-01, 2018-05-01, 2018-06-01. Fit on population orders purchased before T **whose delivery happened before T**; evaluate purchases in [T, T + 1 month).
- Seller history: fit rows use month-start snapshots; evaluation rows use one snapshot frozen at T (no labels from inside the month).
- Models: baseline (fit late rate), logistic C=0.1, GBM {"learning_rate": 0.05, "max_leaf_nodes": 15, "max_iter": 250, "l2_regularization": 1.0}.
- Top 10%: per purchase week inside the month, floor(10% × n) highest scores; weeks crossing a month edge are split.
- The 2018-04-01 fold uses the same fit rows and snapshot as stage 3, and reproduces its April scores (max |difference| = 9.97e-17 over 6,670 orders).

## Results by fold

| cutoff | model | n | late | prevalence | mean_predicted | average_precision | roc_auc | brier | selected | true_late_in_selected | precision_at_top | recall_at_top |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2018-04-01 | baseline | 6670 | 306 | 4.6% | 6.0% | 0.046 | 0.500 | 0.0440 | 664 | 40 | 6.0% | 13.1% |
| 2018-04-01 | logistic | 6670 | 306 | 4.6% | 7.7% | 0.167 | 0.790 | 0.0418 | 664 | 118 | 17.8% | 38.6% |
| 2018-04-01 | gbm | 6670 | 306 | 4.6% | 7.4% | 0.142 | 0.758 | 0.0426 | 664 | 104 | 15.7% | 34.0% |
| 2018-05-01 | baseline | 6630 | 442 | 6.7% | 7.3% | 0.067 | 0.500 | 0.0623 | 662 | 50 | 7.6% | 11.3% |
| 2018-05-01 | logistic | 6630 | 442 | 6.7% | 11.0% | 0.179 | 0.747 | 0.0614 | 662 | 138 | 20.8% | 31.2% |
| 2018-05-01 | gbm | 6630 | 442 | 6.7% | 9.0% | 0.166 | 0.720 | 0.0611 | 662 | 118 | 17.8% | 26.7% |
| 2018-06-01 | baseline | 5565 | 70 | 1.3% | 7.2% | 0.013 | 0.500 | 0.0160 | 553 | 12 | 2.2% | 17.1% |
| 2018-06-01 | logistic | 5565 | 70 | 1.3% | 5.7% | 0.050 | 0.723 | 0.0156 | 553 | 24 | 4.3% | 34.3% |
| 2018-06-01 | gbm | 5565 | 70 | 1.3% | 4.9% | 0.043 | 0.691 | 0.0154 | 553 | 19 | 3.4% | 27.1% |

## Reading

**Summary.** In each of the three selected monthly cohorts the models keep a ranking signal above the constant reference; over-prediction of probabilities persists in every fold; **temporal stability is not established** (three points, changing cohorts, no intervals).

- AP relative to the constant reference (= late share of the month), logistic: 2018-04-01 ×3.64, 2018-05-01 ×2.69, 2018-06-01 ×3.94. This ratio is not a drift-adjusted stability measure.
- ROC AUC, logistic: 0.790 → 0.747 → 0.723. Three points from different cohorts neither establish stability nor show a significant decline.
- Higher AP within each fold: 2018-04-01 logistic, 2018-05-01 logistic, 2018-06-01 logistic. No interval is given: the months contain 6/5/5 purchase-week segments (partial weeks at month edges included), too few for a week-level bootstrap, so the size of the logistic–GBM gap is not established here.
- Brier: logistic is below its fold's constant baseline in 3 of 3 folds (2018-04-01 0.0418 vs 0.0440, 2018-05-01 0.0614 vs 0.0623, 2018-06-01 0.0156 vs 0.0160). The constant itself is the fit late rate, so it is also miscalibrated when the month's late share moves.
- Mean predicted vs observed late share (logistic): 2018-04-01 7.7% vs 4.6%, 2018-05-01 11.0% vs 6.7%, 2018-06-01 5.7% vs 1.3%. Over-prediction from stage 3 persists in every fold; probabilities are not usable as risk levels.
- Late share differs a lot by month, and AP moves with it; compare AP with its own month's baseline, not across months.

## Labels still unknown at each cut-off (excluded from the fit)

| cutoff | fit_rows | fit_late_rate | pending_at_T | pending_late_rate | pending_last_delivery |
|---|---|---|---|---|---|
| 2018-04-01 | 59299 | 6.0% | 3814 | 39.4% | 2018-09-19 23:24:07 |
| 2018-05-01 | 67022 | 7.3% | 2761 | 17.1% | 2018-09-19 23:24:07 |
| 2018-06-01 | 74023 | 7.2% | 2390 | 20.6% | 2018-10-11 16:41:14 |

Orders still in transit at T are disproportionately late. Excluding them is the price of not using future information; it also tilts the fit toward orders that arrived quickly.

## How each evaluation month shrinks to the modelled population

| cutoff | purchased_in_month | estimated_week_in_window | final_A_or_L | single_seller | outside_window | U_or_X_inside_window | median_estimated_days_all_purchases | median_estimated_days_modelled | eval_rows |
|---|---|---|---|---|---|---|---|---|---|
| 2018-04-01 | 6939 | 6939 | 6798 | 6670 | 0 | 141 | 24.0 | 24.0 | 6670 |
| 2018-05-01 | 6873 | 6862 | 6738 | 6630 | 11 | 124 | 22.0 | 22.0 | 6630 |
| 2018-06-01 | 6167 | 5732 | 5665 | 5565 | 435 | 67 | 28.0 | 27.0 | 5565 |

Purchases whose estimated week falls after the approved window are not in the population: 2018-04-01 0 of 6,939 (0.0%), 2018-05-01 11 of 6,873 (0.2%), 2018-06-01 435 of 6,167 (7.1%). Median promised days, all purchases → modelled: 2018-04-01 24 → 24, 2018-05-01 22 → 22, 2018-06-01 28 → 27. The cut removes long-promise orders, so the later the fold, the more the evaluation group is selected. It also keeps only orders whose final outcome is A or L, which is known only after the fact. Treat the 2018-06-01 fold as the least comparable.

## Limits

- Not a new test: the months were already seen. No model or parameter was chosen from these results.
- Three folds, one month each, no intervals, different cohorts: this shows whether a ranking signal is present in each month, not whether performance is stable or how large a difference is.
- Population conditioned on a final A/L outcome; U, X and multi-seller orders are not scored.
- `estimated_days` assumption (stored estimate = estimate shown at checkout) applies to every fold.

## Blocking checks

| check | expected | actual | pass |
|---|---|---|---|
| stage 3 report is current | True | True | True |
| stage 3 is not blocked | True | True | True |
| raw files unchanged since stage 1 | True | True | True |
| stage 3 built on the current mart | True | True | True |
| independent verification exists for this stage-3 run | True | True | True |
| independent verification reports all_match | True | True | True |
| independent verification is bound to the current stage-3 files | True | True | True |
| 2018-04-01: fit uses only labels delivered before T | True | True | True |
| 2018-04-01: fit uses only purchases before T | True | True | True |
| 2018-04-01: eval purchases inside [T, T+1 month) | True | True | True |
| 2018-04-01: no eval order in the fit | 0 | 0 | True |
| 2018-04-01: eval seller snapshot frozen at T | ['2018-04-01 00:00:00'] | ['2018-04-01 00:00:00'] | True |
| 2018-04-01: every seller snapshot holds only labels delivered before its T | True | True | True |
| 2018-04-01: eval block has both classes | True | True | True |
| 2018-05-01: fit uses only labels delivered before T | True | True | True |
| 2018-05-01: fit uses only purchases before T | True | True | True |
| 2018-05-01: eval purchases inside [T, T+1 month) | True | True | True |
| 2018-05-01: no eval order in the fit | 0 | 0 | True |
| 2018-05-01: eval seller snapshot frozen at T | ['2018-05-01 00:00:00'] | ['2018-05-01 00:00:00'] | True |
| 2018-05-01: every seller snapshot holds only labels delivered before its T | True | True | True |
| 2018-05-01: eval block has both classes | True | True | True |
| 2018-06-01: fit uses only labels delivered before T | True | True | True |
| 2018-06-01: fit uses only purchases before T | True | True | True |
| 2018-06-01: eval purchases inside [T, T+1 month) | True | True | True |
| 2018-06-01: no eval order in the fit | 0 | 0 | True |
| 2018-06-01: eval seller snapshot frozen at T | ['2018-06-01 00:00:00'] | ['2018-06-01 00:00:00'] | True |
| 2018-06-01: every seller snapshot holds only labels delivered before its T | True | True | True |
| 2018-06-01: eval block has both classes | True | True | True |
| fold 2018-04-01 reproduces stage-3 test scores for its month | True | True | True |
| evaluation months are inside the stage-3 test period (stability study, not a new test) | True | True | True |
