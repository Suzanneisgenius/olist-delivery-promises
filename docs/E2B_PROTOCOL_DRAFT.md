# E2b protocol — DRAFT (not registered, not run)

Machine-readable settings: `config/e2b_features_draft.yaml`. E1 stays sealed: E2b changes no E1 file, freeze or
verdict, reads E1 outputs only as inputs and writes only under `outputs/e2b/`. This draft was written on 2026-10-25,
after E1 was scored, so its design is informed by E1's evaluation results (see "What this study can and cannot show").

## Why this study

E1's registered residual diagnostic on V ran before E was opened and flagged one group. For the selected HGB setting
D3, orders in the longest predicted-duration quartile had 89.90% coverage against 93.08% overall (3,011 orders,
−3.17 pts; rule: at least 500 orders and at least 3 pts; `outputs/e1/select/selection.json`). The registered response
is a feature-group proposal that the owner accepts or declines. E1 added none (`features_added: none`), and
`docs/E1_DECISIONS.md` has no entry recording that decision. That gap belongs to the E1 wording revision, not to E2b.

V also suggests that model capacity is not the limit: the eight HGB settings span 0.8% in V loss (1.2627 to 1.2725),
and none of the three linear changes reached the 1% adoption bar. E2b therefore adds information, not a model class:
one pre-specified group of two destination-history features, with D3's hyperparameters held fixed.

## Questions

| | Question | Work | Judged by |
|---|---|---|---|
| Q1 | Does feature group G lower forecast loss? | D3 vs D3 + G, same hyperparameters, fitted on F0, scored on V | Adoption rule below (at least 1% lower V integer-day pinball), reported with a V week-cluster interval |
| Q2 | Does G act where the flag pointed? | V coverage by predicted-duration quartile and by seller-history group, D3 vs D3 + G | Descriptive; expectation only |
| Q3 (optional) | Does lower loss give a shorter promise? | If adopted: refit on F, one shift on C, scored once on E against E1's frozen D* | E1's practical rule and monthly reliability; an exploratory second look at E |

Whether Q3 is part of E2b is decided at registration, never after Q1 has been seen.

## Feature group G (exactly these two features)

Both are built at the row's snapshot time T under E1's U rule (start of the purchase month, in every segment), from
the history E1 already uses for seller features: single-seller orders with final outcome A or L delivered before T.
The label is E1's `required_days` (delivered calendar day − purchase calendar day).

| Feature | Group key | Value |
|---|---|---|
| `lane_hist_q90_days` | (`seller_state`, `customer_state_reported`) | 90% quantile (inverted CDF) of `required_days` on the lane, shrunk toward the customer-state value |
| `dest_zip3_hist_q90_days` | first three digits of `customer_zip_code_prefix` (read as text, so leading zeros are kept) | 90% quantile of `required_days` in the zip3 area, shrunk toward the customer-state value |

Shrinkage for a group with n known orders and raw quantile q_g: (n · q_g + k · q_parent) / (n + k), with k = 20
(E1's seller-history `smoothing_k`). The parent is the customer state's quantile at T, or the overall quantile at T
when the state has no known orders; n = 0 gives the parent value. Group counts are logged for diagnostics and are not
features.

Why these two: long promised durations come mostly from long or remote routes. D3 has depth 2, so a seller-state by
customer-state effect has to be assembled from two categorical splits, and `distance_km` does not separate a state
capital from its interior. Olist's own estimate (`estimated_days`) stays excluded, as in D*, so a comparison with
Olist's promise would not be circular.

## Fixed (copied from E1, not re-chosen)

| Item | Value |
|---|---|
| Segments and label cut-offs | F0, V, F, C, E exactly as in `config/date_model_e1.yaml`; partition ids must equal `outputs/e1/prep/partition_manifest.csv` |
| Population | E1's: estimated week in the approved window, final outcome A or L, single seller |
| Model | `HistGradientBoostingRegressor(loss='quantile')`, q = 0.90, max_depth 2, max_iter 400, learning_rate 0.05, min_samples_leaf 100, l2_regularization 1.0, no early stopping, random_state 20261015; categorical: `customer_state_reported`, `seller_state`, `purchase_dow` |
| Base features | D*'s 13 features, unchanged (`outputs/e1/freeze/FREEZE.json`, `feature_rules`) |
| Calibration | s_i = y_i − ŷ_i on C, k = ceil((n + 1) q), d(x) = max(1, ceil(ŷ(x) + s_(k))), with E1's 1e-9 tolerance |
| Bootstrap | V: purchase weeks, iid with replacement, 2,000 replicates, seed 20261105. E: E1's saved week draws, so every E comparison is paired with E1's |

No grid search, no second feature group, no other quantile level and no other calibration set.

## Decision rules (written before the run)

- **Reproduce first.** D3 refitted on F0 must reproduce E1's saved V predictions
  (`outputs/e1/select_repro1/v_predictions_per_order.csv.gz`) and V integer-day pinball 1.2626567040265668 within
  1e-9, or nothing is reported.
- **Q1 adopt** if L_V(D3 + G) ≤ 0.99 · L_V(D3) on E1's integer-day pinball (`v_pinball_int`). Report
  Δ = L_V(D3 + G) − L_V(D3) and its 95% week-cluster interval. An interval that contains 0 is not evidence of no
  effect.
- **Not adopted:** reported as "below the adoption bar"; Q3 does not run.
- **Not evaluable:** a fit failure or a non-finite prediction. No substitute feature or setting is chosen.
- **Q3** (only if adopted and included at registration): G* = D3 + G refitted on F, with one shift on C. On E,
  report unshifted integer pinball (paired with D*), coverage, mean promised days, monthly coverage, and E1's
  practical rule (mean days ≤ reference − 1.0 and coverage ≥ reference − 1.0 pt) against D* and against B1c
  separately, plus E1's monthly-reliability rule. The registered rounding is E1's round-up rule. Round-down, as in
  `scripts/e1_rounding_rules.py`, is reported beside it, labelled, and never decides.
- E2b never restates or revises an E1 verdict.

## Expectations, not criteria

Written before the run; a mismatch is reported, not tuned away.

- Q1: the V gain is small, of the order of the 2% HGB-over-linear gap on V, and may fall below the 1% bar, because
  `distance_km` and the two state variables already carry much of the route information.
- Q2: the coverage gap in the longest quartile narrows but does not close.
- Q3: even with lower loss, mean promised days change by less than one day. E1's calibrated policies cover 96–97% of
  E for a 90% target, and a feature group does not address the change between C and E.

## Information rules

- A feature value comes only from orders delivered before the row's snapshot T, and T is never after the row's
  purchase time. A violation raises an error, as `features.seller_snapshot` does.
- G inherits E1's final-status filter. In the whole file, 6 orders have a valid delivery record but final status
  canceled (`outputs/stage6a/record_status_conflicts.csv`). The history is every single-seller order in the mart,
  not only the approved window (`e1_data.load`), so up to 5 of them (delivered October to November 2016) can be
  missing from every later snapshot, and 1 (delivered 2018-03-21) from snapshots taken from 2018-04-01. Whether each
  is a single-seller order is not yet checked. This is a bound, not a claim of no look-ahead, and it assumes each
  delivery was recorded when it happened, which the file cannot show.
- Lanes and zip3 areas with no history take the parent value. No category is built from E.

## What this study can and cannot show

E was examined in E1, and this protocol was written after E1's results were known. Q1 uses only F0 and V. Both were
used for selection in E1, but no result for G has been computed on them. Q3 is a second look at E: it is exploratory
and cannot confirm a gain. The Olist file has no later period that could serve as a fresh test.

## Code and file boundaries

- New code lives in a top-level `e2b/` package with its own tests in `e2b/tests/` and imports `olist_analytics` read
  only. Nothing under `src/` changes (E1's code fingerprint), and nothing is added to `tests/` (the E1 suite stays at
  362 tests).
- Outputs go only under `outputs/e2b/`. E1 files are read, never written.
- The run needs the raw Kaggle CSVs, which are not in the repository, and recipe C's environment
  (`docs/REPRODUCE_E1.md`).

## Before anything runs

1. The author decides whether Q3 is included and confirms or edits the YAML; its SHA-256 is logged in
   `docs/E1_DECISIONS.md`, as for E2a.
2. Code is written and tested on synthetic fixtures first, including a red/green test that a label delivered at T is
   refused.
3. The registered run computes Q1 and Q2 and writes the adoption decision before any C or E output for G exists. Q3,
   if included, runs once after that.

Out of scope: a new model class or hyperparameter search, other feature groups, `estimated_days` as a feature,
online or adaptive recalibration, a new Olist cohort and any change to E1.
