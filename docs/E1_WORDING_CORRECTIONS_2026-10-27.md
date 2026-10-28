# E1 wording corrections and audit notes (2026-10-27)

Applies to the sealed v6 documents in `documents/current/` (main report, supplement) and to this repository's
front page. Those PDFs, `outputs/e1/freeze/FREEZE.json`, the configuration, the fitted models and every saved E1
result are unchanged. No model was fitted and no analysis was run for this note: every number below is quoted from
the saved file named next to it. The registered verdicts are unchanged.

The note has three parts, kept apart on purpose:

- **Part A** corrects the wording of conclusions the reports already draw. It adds no result.
- **Part B** records audit findings that the reports do not cover. They are open questions, not results, and no
  effect size is claimed for them.
- **Part C** lists corrections to the diagnostics page made before it was first published. The page is a reading aid
  and not part of E1.

Sources: the external review of 2026-10-25 (findings F2, F3, F5, F6, F7, F8, F9, F10), the review of the diagnostics
page of 2026-10-27 and the review of handoff v5 of the same day.

## Part A. Wording corrections to existing conclusions

### A1. H3 holds under the registered rounding rule (review F2)

Where: main report, summary (page 2), §4 table, end of §5 ("the registered H3 verdict stands") and §6 conclusion.
As written: "HGB did not clear the 1-day bar", without a condition.

Read as: under the registered rule, which rounds the calibrated bound up, the HGB policy D* was 0.32 days shorter
than the calibrated state rule B1c at +0.61 coverage points. That is below the 1-day bar, so H3 is recorded as not
supported. Under rounding down, the post-hoc rule that §5 shows keeps the coverage event, the same comparison is
1.32 days shorter at +0.18 points. The registered verdict therefore describes the registered rounding rule as much as
the two models. The post-hoc figure does not replace the registered result. Against the retained rule B0 the
replacement standard is not met under either rule: D* promises 3.37 days more rounded up and 2.37 days more rounded
down.

Basis: `outputs/e1/score/comparisons.json` (claim C07); `outputs/e1/posthoc_m4/rounding_comparisons.csv`.

### A2. The loss comparison behind the research question (review F3)

Where: main report §1–§5. The question asks when lower forecast loss fails to give better promised dates, but the
v6 main report does not print the loss of the two models.

Add: HGB is the lower-loss model in both periods. On V, the selected HGB setting D3 had pinball loss 1.26266 against
1.28856 for the linear model C0, 2.01% lower; V was also used to select the models, so this comparison favours the
selected setting. On E, before calibration, HGB's pinball loss was 1.324 against 1.417 for the linear model, 6.5%
lower, at uncalibrated coverage 91.08% and 88.33%. Both comparisons are of whole-day promises before any calibration
shift, not of the raw continuous forecasts: C04 uses `v_pinball_int`, and C12 the `promise_unshifted` columns.

Basis: claim C04 (`outputs/e1/select/*.csv`) and claim C12 (`outputs/e1/score/e_promises_per_order.csv.gz`), both
checked by `AGENT_REVIEW/verify_all.sh` step 09. C12's `stated_in` field gives "§1, §5", where the v6 main report
does not print these numbers; this note is where they are stated. `AGENT_REVIEW/claims.json` is not changed.

### A3. What "frozen" covers (review F5)

Where: main report §3 and §4, and the figure caption ("frozen policies").

Read as: "frozen" means that the fitted models and the calibration shifts were fixed before E was scored. The
seller-history features were not frozen. Under the registered feature rule U, each order's seller history is taken
at the start of its purchase month, so for E it includes orders delivered during E before that date. Such
information would be available in operation, but "frozen" should not be read as "uses only information up to
1 April 2018". The fixed-date rule O, with an E snapshot on 1 April 2018, is used for the stage-7 reproduction B2
only.

Basis: `config/date_model_e1.yaml`, `seller_snapshot` ("U = frozen model parameters + monthly-refreshed history
features"; "O ... for B2 only"); `src/olist_analytics/e1_data.py` (`snapshot_times`).

### A4. Coverage on C after rounding down is an identity (review F6)

Where: main report §5 ("Coverage on C would fall from 91.1–91.2% to 90.01%, which still meets the rank bound");
supplement S3b ("Rounding down meets the rank bound on C for every policy").

Read as: for a continuous forecast, rounding the calibrated bound down covers exactly the k orders whose residual is
at most the k-th smallest one, so coverage on C equals k/n = 15,352/17,056 = 90.01% by construction (when the k-th
residual is untied). It is an identity, not an empirical check that passed.

Basis: the calibration rule in main report §3 (k = ⌈(n + 1) · 0.9⌉, n = 17,056).

### A5. Name of the bootstrap (review F9)

Where: main report §4.
As written: "Intervals are week-block bootstrap intervals over 17 purchase weeks".

Read as: week-cluster bootstrap intervals, in which whole purchase weeks are resampled with replacement (the `iid`
intervals in `outputs/e1/score/comparisons.json`). The `moving2` intervals in the same file resample pairs of adjacent
weeks and are a sensitivity check.

### A6. Which numbers are recomputed (review F7)

Where: the repository's front page and `AGENT_REVIEW/REVIEW_BRIEF.md`.
As written: "every reported number is recomputed independently".

Read as: the verifier checks the 26 numerical claims marked `auto` in `AGENT_REVIEW/claims.json` against saved
evidence, recomputing metrics from saved per-order files where they exist. Some checks compare saved aggregates rather
than rebuilding them from raw data: C27, for example, reads the upstream sample-flow counts from a saved CSV and checks
only the final cohort against the saved predictions. The remaining 3 of the 29 entries are handled separately: the
test count (C17) by the test step, and two qualitative provenance statements (C18, C19). Some numbers in the main
report are in no check at all, for example the mean actual delivery time of 6.2 days in July and the June–July
coverage of 98.3–98.5% in §5. The front page now says this; `REVIEW_BRIEF.md` and `claims.json` are left as they
were reviewed.

## Part B. Audit findings not covered by the reports

These are reported, not resolved. Nothing here changes a result, and none of them is shown to be small.

### B1. The final-status filter can use information from after a snapshot (review F10)

E1's populations and seller histories keep orders whose outcome bucket is A or L
(`config/model.yaml`, `src/olist_analytics/features.py`). The bucket comes from `order_status` as it stood when the
data were exported (`sql/order_outcome_buckets.sql`: `canceled` and `unavailable` become X). An order delivered before
a snapshot T but recorded as canceled afterwards is therefore left out of the history at T because of information from
after T.

In the whole order file, 6 records have a customer delivery date but final status `canceled`
(`outputs/stage6a/record_status_conflicts.csv`): 5 delivered in October and November 2016 and 1 on 2018-03-21. This
note reports only that count of candidate records. It has not been checked whether any of them is a single-seller
order in E1's history, which snapshots and features they would enter, or what difference they would make to any E1
number. The count is not evidence that the effect is negligible. The file also cannot show whether each delivery date
was recorded when the delivery happened. Answering these questions needs the raw data, and no such check is part of
this note.

### B2. Reproduction recipe B was accepted on the v2 snapshot only (review F8)

The end-to-end acceptance run of recipe B (`outputs/e1/recipeB_acceptance/`) used the sealed v2 snapshot archive as
input. `docs/REPRODUCE_E1.md` also allows a review package as `SNAP`; that path has not been run. The code blocks
start with `set -euo pipefail`, so pasting one into an interactive shell closes the shell at the first failing
command: save each block as a script and run it with `bash`, as the acceptance run did.

## Part C. Diagnostics page: corrections before first publication

The page in `docs/diagnostics_page/` aggregates saved stage-3, stage-5 and E1 outputs. An earlier private version was
reviewed on 2026-10-27. These corrections were made before the page was first published; no E1 number is affected.

- **Weekly picks.** The all-months view of the monthly refit ranked each purchase week across folds, mixing two model
  versions in weeks that span two months. Picks now follow each stage's own rule (stage-3 test set by purchase week;
  each stage-5 fold by purchase week), and month views add up to all months. Example: logistic regression at a 1%
  weekly share now picks 180 orders and includes 32 late ones (previously 182 and 33). The default 10% figure,
  280 of 818 late orders, is unchanged.
- **Random baseline.** It now uses the same weekly budgets as the model (the sum of k × L / n over the same groups).
  At the default 10% share the expected count changes from 81.475 to 81.547 late orders, and the ratio from 3.44 to
  3.43.
- **Days at each coverage level (Table 3).** The table said each shift reaches "the same coverage" but showed only
  mean days. It now shows the coverage each policy actually reached beside its mean days, and says that whole-day steps
  make a policy overshoot the level. At the 90% level the state rule reached 90.75%, the linear model and HGB 90.02%.
  Values from `outputs/e1/posthoc_m4/matched_coverage_E.csv`, unchanged.
- **Recalibration.** The page no longer treats a 30-day reporting lag as making a month's labels complete, or the
  visible direction of the error as a reason a test would show little. A fixed lag would need an order-level audit of
  label availability, the months left are small and already inspected, and overprediction alone does not show whether
  a later correction would help.
- **Wording.** The page no longer says that late orders "were on the follow-up list before they arrived": it replays
  historical weeks with saved predictions, no order was followed up, and nothing shows that a delay could have been
  prevented. It no longer says that recalibration would not change the picks: only one strictly increasing transform
  applied to the whole batch leaves them unchanged.

Basis: `docs/diagnostics_page/aggregate.py` and `check_budget.py`, which rechecks all 540 rows of
`data/risk_budget.json` with `modeling.top_share_by_week`.
