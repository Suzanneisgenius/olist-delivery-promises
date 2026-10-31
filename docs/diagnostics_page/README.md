# Diagnostics page (reading aid)

A four-view web page. Views 01 to 03 are built only from saved outputs; view 04 adds illustrative calculations and
seeded simulations, and its one table of project numbers is copied from saved results. It changes no
registered analysis, fitted model or prediction.

| View | Question | Built from |
|---|---|---|
| Risk prioritization | With limited staff, which orders should be checked first? | `outputs/stage3/test_predictions.csv`, `outputs/stage5/fold_predictions.csv` |
| Probability reliability | When a score says 10% risk, is the late rate really near 10%? | the same two files |
| Delivery promises | Is a more complex model worth switching to for promised dates? | `outputs/e1/score/policy_table.csv`, `outputs/e1/posthoc_m4/` |
| The mathematics | Why is a promise a quantile, and where does its guarantee stop? | no data file: illustrative numbers, a toy simulation, and one table copied from the mathematical note, the notebook and `e1_policies.json` |

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
jsDelivr); its typefaces come from Google Fonts: Atkinson Hyperlegible Next for the text and Kalam for hand-written
notes. The filters are kept in the address, so a refresh or a shared link shows the same view.

The page is styled as a study notebook. Colour in the charts is kept for data; the author's own marks (view numbers,
margin labels, a boxed key result in each step of view 04 and short suggestions beside its demonstrations) are in a
violet pen with a highlighter. Motion is limited to a short fade when the reader switches views and one highlighter
stroke on the opening's two headline numbers, and is switched off when the reader's system asks for reduced motion.

View 04, the mathematics, sets out the argument behind the promised-dates comparison in four steps: why a delivery
promise is a quantile, why a predicted quantile still needs calibrating, why whole-day dates need separate treatment,
and how to assess coverage when the data change. Steps 1 to 3 each have a small demonstration on illustrative numbers,
and the mathematical note proves their main results. Step 4 writes the observed over-coverage exactly as three terms
(calibration rule, residual distributions at the shift, rounding) and reads them post hoc from the saved rounding
comparison. A fold, "Going further", summarises coverage bounds without exchangeability (Barber, Candès, Ramdas and
Tibshirani, 2023) and weighted calibration under covariate shift (Tibshirani, Barber, Candès and Ramdas, 2019), with a
toy simulation. Formulas are typeset with KaTeX from jsDelivr; without it the TeX source stays readable. A link to a
step (`#m1` to `#m4`) opens the view at that step and stays in the address; a link inside a fold opens the fold.

A "My contribution" panel before the footer summarises the author's confirmed roles from `AUTHORSHIP.md` and links to
that statement. The panel and its top link are hidden automatically if its body is emptied. Browsers do not
let a page opened from disk read its data files, so view it over HTTP:

    python3 -m http.server 8000 --directory docs/diagnostics_page      # then open http://localhost:8000

`.github/workflows/pages.yml` publishes `index.html` and `data/` to GitHub Pages after rebuilding the data and
comparing it with the committed files.
