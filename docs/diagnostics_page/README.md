# Diagnostics page (reading aid)

A three-view web page built only from saved outputs. It fits no model, adds no prediction and changes no registered
result. It is not part of E1's registered analysis: E1 numbers are copied from `outputs/e1/`, not recomputed.

| View | Question | Built from |
|---|---|---|
| Risk prioritization | With limited staff, which orders should be checked first? | `outputs/stage3/test_predictions.csv`, `outputs/stage5/fold_predictions.csv` |
| Probability reliability | When a score says 10% risk, is the late rate really near 10%? | the same two files |
| Delivery promises | Is a more complex model worth switching to for promised dates? | `outputs/e1/score/policy_table.csv`, `outputs/e1/posthoc_m4/` |

Two versions of the risk scores are shown. "Frozen" is the stage-3 model scored once on E1's evaluation orders
(April to July 2018; the script checks that the order sets are equal). "Refit" is the stage-5 monthly refit, each
fold scoring the purchase month after its cut-off (April to June 2018).

## Weekly picks and the random baseline

Each version is picked by the rule its stage was scored with (`modeling.top_share_by_week`): per budget group, the
floor(share × n) orders with the highest scores, ties by row order. The budget group is the purchase week of the whole
test period for the frozen model (stage 3) and the purchase week within each fold for the refit (stage 5), so a week
that spans two months is never ranked across folds. The picks are made once per version and share; a month view counts
the picked orders purchased in that month, and all months is their sum. For the frozen model a week that spans two
months is ranked once, so one month's picks can be slightly above or below the chosen share.

The random baseline uses the same budgets: a group of n orders with L late and k picks adds k × L / n expected late
orders. `lift_vs_random` is late orders among the picks divided by that expectation.

## What it does not do

- No follow-up took place. The page replays historical weeks: the risk-ranked picks included the late orders it counts,
  which does not show that a delay could have been prevented.
- No recalibration. The planned intercept adjustment was not tested; the reliability view shows diagnostics only. The
  picks depend only on the order of scores within each week, so one strictly increasing transform applied to the whole
  batch would not change them; a recalibration that differs by group or by month could.
- No order-level data: every file in `data/` is an aggregate (months, weekly shares, score bands or policies).
- The table of days at the first shift reaching each coverage level (with the coverage each policy actually reached)
  and the coverage curves are E1's post-hoc diagnostics (`outputs/e1/posthoc_m4/`), labelled as such on the page. The
  registered E1 comparison is unchanged.

## Rebuild and check

Standard library only, read-only with respect to the repository:

    python3 -I docs/diagnostics_page/aggregate.py . docs/diagnostics_page/data

It writes the seven files in `data/` and checks them against the saved metrics: for each stage-5 fold and model, the
top-10% weekly picks (selected and late counts), Brier score, log loss and mean predicted probability; for the stage-3
test set, the top-10% picks and the calibration bins (ten per model); and, at every share from 1% to 30%, that the
months add up to all months. It ends with `ALL CHECKS OK` (exit 0) or `ALL CHECKS FAILED` (exit 1). It also reports
whether the mean predicted risk exceeds the observed late rate in every version, model and month; in the saved outputs
it does.

An independent check of every row of `risk_budget.json` uses the repository's own selection function and pandas
(repository environment):

    PYTHONPATH=src python3 docs/diagnostics_page/check_budget.py . docs/diagnostics_page/data

It ends with `BUDGET CHECK OK` (exit 0).

| File | One row per |
|---|---|
| `risk_budget.json` | version, model, month (or all), weekly share 1–30% |
| `prob_monthly.json` | version, model, month: observed rate with Wilson 95% interval, mean predicted, Brier, log loss |
| `prob_bins.json` | version, model, month, equal-count score band (10 for all months, 5 for one month) |
| `e1_policies.json` | E1 policy: B1c, C*, D* (registered) and B0, Olist (references) |
| `e1_curves.json` | E1 post-hoc coverage curve point, coverage 0.80–0.995 (every 0.05-day shift for C* and D*; every point for the state rule) |
| `e1_matched.json` | E1 post-hoc matched-coverage row |
| `e1_rounding.json` | E1 rounding comparison, round-up and round-down only |

## The page

`index.html` is a standalone page: it reads the seven files from `data/` and draws the charts with d3 (loaded from
jsDelivr). The filters are kept in the address, so a refresh or a shared link shows the same view. Browsers do not
let a page opened from disk read its data files, so view it over HTTP:

    python3 -m http.server 8000 --directory docs/diagnostics_page      # then open http://localhost:8000

`.github/workflows/pages.yml` publishes `index.html` and `data/` to GitHub Pages after rebuilding the data and
comparing it with the committed files.
