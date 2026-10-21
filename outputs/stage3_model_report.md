# Stage 3 — Purchase-time Late-Delivery Risk Model

Public Olist data, **offline simulation** of scoring an order at checkout. Every number comes from `python -m olist_analytics.run_stage3`, which runs only on a READY stage-1 release and writes this file only after every check in §9 passes. Design decisions are in `config/model.yaml`.

## 1. Question and boundary
- At purchase time, can we rank orders by risk of being delivered after the estimated day?
- Label: late (L) = 1, on time (A) = 0. Only orders with a final A/L outcome and a single seller are modelled; the model says nothing about orders that are canceled, never confirmed, or multi-seller.
- Features come only from checkout-time fields plus seller history known at a snapshot time. Whitelist (19): `estimated_days`, `distance_km`, `items_price_sum`, `items_freight_sum`, `freight_ratio`, `weight_g_sum`, `n_item_lines`, `n_distinct_products`, `same_state`, `purchase_hour`, `purchase_dow`, `seller_hist_n_delivered`, `seller_hist_late_rate`, `seller_hist_n_placed`, `seller_hist_handling_median_h`, `seller_age_days`, `customer_state_reported`, `seller_state`, `top_price_category`.
- **Assumption (unverified):** `estimated_days` uses the stored estimated date as if it were the one shown at checkout; there is no version history. §6 shows how much the model depends on it.
- Other stored checkout/profile fields are also assumed available as recorded: the dataset has no historical versions of product weights or geolocation reference tables.

## 2. Population and splits
| step | orders |
|---|---|
| all orders | 99441 |
| estimated week inside approved window | 86729 |
| final outcome A or L (U, X excluded) | 84129 |
| single seller | 83063 |

| split | orders | late | first_purchase | last_purchase | late_rate |
|---|---|---|---|---|---|
| train | 42729 | 2438.0 | 2017-01-07 | 2017-12-31 | 5.7% |
| dev | 20384 | 2652.0 | 2018-01-01 | 2018-03-31 | 13.0% |
| test | 19950 | 850.0 | 2018-04-01 | 2018-07-19 | 4.3% |

Late rate shifts strongly: 5.7% train → 13.0% dev (Feb–Mar 2018 spike) → 4.3% test. The model is trained and judged under drift.

## 3. Label availability (no future labels)
A training or model-selection label is used only if the delivery happened before the relevant cut-off. Seller-history features use the same rule at their snapshot time (`outputs/stage3/seller_snapshots.csv`).

| fit | cutoff | rows_in_split | label_known | excluded_label_unknown | late_share_excluded |
|---|---|---|---|---|---|
| tuning fit (train) | 2018-01-01 | 42729 | 40250 | 2479 | 27.8% |
| final fit (train+dev) | 2018-04-01 | 63113 | 59299 | 3814 | 39.4% |
| model selection (dev) | 2018-04-01 | 20384 | 16577 | 3807 | 39.3% |

- **Cost of the rule:** excluded rows are much more often late (they took longer). Training therefore under-represents slow orders near each cut-off under this delivered-label convention. Using older purchase cohorts with a maturity buffer could reduce this selection at the cost of data and recency; that alternative was not tested in this revision.
- Snapshots: training rows use the start of their purchase month; dev and test rows use a snapshot frozen at the start of their block (no labels from inside the block).
- Historical handling medians exclude orders with invalid stage timestamps; these orders can still contribute known A/L labels to the seller's delay rate.

## 4. Model choice on dev (test not used for model choice)
Model selection at 2018-04-01 uses 16,577 development orders whose labels were already known, including 1,156 late orders (7.0%). Pending development labels are excluded from parameter and family choice.
| family | params | average_precision | roc_auc | brier | precision_at_top |
|---|---|---|---|---|---|
| logistic | {"C": 0.1} | 0.139 | 0.675 | 0.064 | 16.6% |
| logistic | {"C": 1.0} | 0.136 | 0.667 | 0.064 | 16.0% |
| gbm | {"learning_rate": 0.05, "max_leaf_nodes": 15, "max_iter": 250, "l2_regularization": 1.0} | 0.127 | 0.655 | 0.065 | 15.2% |
| gbm | {"learning_rate": 0.05, "max_leaf_nodes": 31, "max_iter": 250, "l2_regularization": 1.0} | 0.122 | 0.646 | 0.065 | 13.9% |
| gbm | {"learning_rate": 0.1, "max_leaf_nodes": 15, "max_iter": 250, "l2_regularization": 1.0} | 0.123 | 0.649 | 0.065 | 14.5% |
| gbm | {"learning_rate": 0.1, "max_leaf_nodes": 31, "max_iter": 250, "l2_regularization": 1.0} | 0.121 | 0.644 | 0.066 | 14.6% |

Chosen: logistic `{"C": 0.1}`, gradient boosting `{"learning_rate": 0.05, "max_leaf_nodes": 15, "max_iter": 250, "l2_regularization": 1.0}`. Both were then refit on train + dev (labels known before 2018-04-01), frozen, and evaluated on test. This protocol correction re-evaluates a test set already inspected in v0.3.0; it is not a fresh confirmatory holdout. No parameters or headline family were chosen from the test results.

## 5. Test results (2018-04-01 → 2018-07-19)
| model | n | late | prevalence | average_precision | roc_auc | brier | brier_skill_vs_baseline | precision_at_top | recall_at_top |
|---|---|---|---|---|---|---|---|---|---|
| baseline | 19950 | 850 | 4.3% | 0.043 | 0.500 | 0.041 | 0.000 | 3.6% | 8.5% |
| logistic | 19950 | 850 | 4.3% | 0.123 | 0.761 | 0.040 | 0.024 | 13.0% | 30.5% |
| gbm | 19950 | 850 | 4.3% | 0.111 | 0.721 | 0.041 | 0.011 | 11.4% | 26.6% |

- **Finding.** Both models rank late orders far better than the constant baseline. Logistic regression: AP 0.123 vs baseline 0.043 (= prevalence); ROC AUC 0.761.
- **Top 10% per purchase week** (hypothetical review capacity, not a real team resource): logistic precision 13.0% vs 3.6% for one seeded random draw (expected random precision 4.3%), catching 30.5% of all late orders.
- **Uncertainty** (purchase-week bootstrap, 1000 reps): AP logistic 0.084–0.169, gbm 0.079–0.148; gbm − logistic -0.012 (-0.021 to -0.004). The paired interval favours logistic. These intervals are conditional on the fitted models and sampled purchase weeks, not model-refitting uncertainty or protection against serial dependence across weeks.
- **Reading:** logistic was selected using available development labels. Any explanation of cross-period performance, including overfitting or drift, remains an interpretation rather than a causal diagnosis.

### Calibration
Mean predicted risk on test: logistic 7.29%, gbm 6.96%; observed 4.26%. Predicted risk exceeds observed frequency in 10/10 logistic bins and 10/10 gradient-boosting bins. The mismatch is consistent with prevalence drift; these results do not establish its cause. Use ranking metrics for this benchmark; raw probabilities need validation before operational use. No recalibration was fitted. It can use an independent earlier calibration set with labels available before scoring; it does not require fitting on the final test labels.

| bin | n | mean_predicted | observed_rate | model |
|---|---|---|---|---|
| 0 | 1995 | 1.76% | 0.30% | logistic |
| 1 | 1995 | 2.90% | 0.80% | logistic |
| 2 | 1995 | 3.75% | 1.55% | logistic |
| 3 | 1995 | 4.53% | 1.90% | logistic |
| 4 | 1995 | 5.33% | 2.21% | logistic |
| 5 | 1995 | 6.22% | 3.26% | logistic |
| 6 | 1995 | 7.37% | 3.81% | logistic |
| 7 | 1995 | 9.00% | 5.61% | logistic |
| 8 | 1995 | 11.85% | 8.47% | logistic |
| 9 | 1995 | 20.17% | 14.69% | logistic |
| 0 | 1995 | 1.81% | 0.70% | gbm |
| 1 | 1995 | 2.73% | 1.35% | gbm |
| 2 | 1995 | 3.42% | 1.45% | gbm |
| 3 | 1995 | 4.08% | 2.61% | gbm |
| 4 | 1995 | 4.80% | 2.51% | gbm |
| 5 | 1995 | 5.65% | 3.91% | gbm |
| 6 | 1995 | 6.72% | 4.61% | gbm |
| 7 | 1995 | 8.32% | 5.21% | gbm |
| 8 | 1995 | 11.30% | 7.37% | gbm |
| 9 | 1995 | 20.81% | 12.88% | gbm |

## 6. Sensitivity
| variant | model | average_precision | roc_auc | precision_at_top | recall_at_top |
|---|---|---|---|---|---|
| without estimated_days | logistic | 0.068 | 0.647 | 7.9% | 18.4% |
| without estimated_days | gbm | 0.065 | 0.631 | 7.1% | 16.6% |
| test seller features refreshed monthly | logistic | 0.132 | 0.767 | 13.6% | 31.9% |
| test seller features refreshed monthly | gbm | 0.113 | 0.725 | 11.6% | 27.2% |

- **Without `estimated_days`** AP falls to 0.068 (logistic) / 0.065 (gbm). Much of the skill rests on the estimate assumption in §1.
- **Monthly seller refresh at test time** (instead of one frozen snapshot): logistic AP 0.132. Fresher history helps a little; the frozen result in §5 is the headline because it needs no online-update assumption.

## 7. Where it works and where it does not (logistic scores, test; headline model chosen on dev)
| segment | value | n | prevalence | average_precision | precision_at_top | recall_at_top |
|---|---|---|---|---|---|---|
| purchase month | 2018-04 | 6670 | 4.6% | 0.167 | 17.8% | 38.6% |
| purchase month | 2018-05 | 6630 | 6.7% | 0.140 | 16.5% | 24.7% |
| purchase month | 2018-06 | 5565 | 1.3% | 0.045 | 4.7% | 37.1% |
| purchase month | 2018-07 | 1085 | 2.9% | 0.057 | 6.5% | 21.9% |
| customer state | BA | 638 | 15.4% | 0.258 | 23.6% | 13.3% |
| customer state | DF | 448 | 3.8% | 0.124 | 5.4% | 11.8% |
| customer state | ES | 397 | 12.3% | 0.220 | 9.7% | 6.1% |
| customer state | GO | 371 | 4.0% | 0.105 | 6.9% | 13.3% |
| customer state | MG | 2263 | 3.9% | 0.119 | 9.1% | 22.5% |
| customer state | PR | 1020 | 2.8% | 0.052 | 3.2% | 10.3% |
| customer state | RJ | 2162 | 4.9% | 0.112 | 9.1% | 18.1% |
| customer state | RS | 954 | 2.7% | 0.046 | 6.7% | 23.1% |
| customer state | SC | 683 | 2.6% | 0.081 | 4.9% | 16.7% |
| customer state | SP | 9453 | 2.4% | 0.069 | 6.0% | 24.3% |

Segments with < 300 orders or < 10 late orders are not shown. AP depends on prevalence, so compare each row with its own prevalence, not with other rows. Each row reselects its top fraction within that segment and week; these subgroup precision/recall values do not measure the composition of the global review queue.

## 8. What the models use (permutation importance on test, AP drop)
- logistic: estimated_days (+0.052), seller_hist_n_delivered (+0.042), customer_state_reported (+0.037), seller_hist_n_placed (+0.030)
- gbm: customer_state_reported (+0.047), estimated_days (+0.039), distance_km (+0.017), seller_hist_handling_median_h (+0.003)
- Predictive use only. A feature with high importance is not a cause of lateness.

## 9. Blocking checks
| check | expected | actual | pass |
|---|---|---|---|
| population == train + dev + test | 83063 | 83063 | True |
| splits ordered by purchase time (max train < min dev, max dev < min test) | True | True | True |
| tuning fit uses only labels delivered before T1 | True | True | True |
| final fit uses only labels delivered before T2 | True | True | True |
| model selection uses only dev labels delivered before T2 | True | True | True |
| every seller snapshot holds only labels delivered before its T | True | True | True |
| no test row is in any fit | 0 | 0 | True |
| feature matrix == whitelist (no forbidden column) | ['customer_state_reported', 'distance_km', 'estimated_days', 'freight_ratio', 'items_freight_sum', 'items_price_sum', 'n_distinct_products', 'n_item_lines', 'purchase_dow', 'purchase_hour', 'same_state', 'seller_age_days', 'seller_hist_handling_median_h', 'seller_hist_late_rate', 'seller_hist_n_delivered', 'seller_hist_n_placed', 'seller_state', 'top_price_category', 'weight_g_sum'] | ['customer_state_reported', 'distance_km', 'estimated_days', 'freight_ratio', 'items_freight_sum', 'items_price_sum', 'n_distinct_products', 'n_item_lines', 'purchase_dow', 'purchase_hour', 'same_state', 'seller_age_days', 'seller_hist_handling_median_h', 'seller_hist_late_rate', 'seller_hist_n_delivered', 'seller_hist_n_placed', 'seller_state', 'top_price_category', 'weight_g_sum'] | True |
| baseline AP == test prevalence | 0.0426065163 | 0.0426065163 | True |

## 10. Limits
- Offline simulation on a public snapshot; not a deployed model, no business outcome measured.
- Population excludes U, X and multi-seller orders (selection; see §2).
- Probabilities are mis-calibrated under drift (§5); use ranks, or recalibrate on recent labelled data.
- Distance is a zip-prefix straight-line proxy; seller history uses single-seller orders only.
- The review-score association (optional module 3b) is not part of this stage.

## 11. Decisions for the owner
1. Accept logistic (best dev AP) as the stage-3 headline model, with the other family reported as the comparison.
2. Accept the `estimated_days` assumption with the sensitivity result shown next to it.
3. Keep probabilities out of any portfolio claim until recalibrated; report AP, top-10% precision/recall.
