# Stage 6a — Survival Analysis Feasibility Review (rev. 2, v0.5.2)

Status: **review only — no survival model has been fitted. Stage 6b is not recommended to start yet**: the
estimand, population and evaluation plan must first be chosen by the owner (§6). Stopping here with a
documented feasibility result is a valid outcome.

Rev. 2 (v0.5.2) adds two qualifiers from the v0.5.1 review: the as-of view is an event-date reconstruction, and
"no censoring" in the common cohort holds under final-file retrospective evaluation. Rev. 1 answered the v0.5.0 review: explicit exclusive observation time; final-file view separated from the
as-of view; recent U renamed to *candidates*; record–status conflicts isolated; D1/D3/D4 withdrawn as
recommendations. Numbers come from `python -m olist_analytics.survival_audit` (`outputs/stage6a/`,
tables in `outputs/stage6a/feasibility_tables.md`). Rules are tested in `tests/test_stage6a.py`.

## 1. What a survival model would estimate

- Time origin: purchase. Event: a delivery record (`order_delivered_customer_date`).
- S(t | x) = P(no delivery yet t days after purchase). Deadline d_i = end of the estimated day − purchase.
- The project's late rule (delivered day > estimated day) is exactly "delivery time ≥ d_i", so
  **P(late_i) = S(d_i | x_i)**, not 1 − S. (Test: `test_late_iff_delivery_time_reaches_deadline...`.)

## 2. Time conventions and two views of each order

- The stage-1 boundary is a **date**, 2018-09-03, inferred from activity; stage 1 counts deliveries after that
  *day* (37). The exclusive observation time is therefore **2018-09-04 00:00** (primary). The midnight reading,
  2018-09-03 00:00, is a sensitivity. Neither is a confirmed extraction time (last timestamp in the file: 2018-10-17).
- **Final-file category**: what the last record says (A/L/U/X, dates). It describes the data; it is not
  knowledge available at an earlier time.
- **Event-date reconstructed state at a cut c** (exclusive). It is rebuilt from the event dates in the final file,
  assuming each event was recorded when it happened; it is **not** a snapshot of what the system actually showed at c,
  and historical information availability is not verified. States: `NOT_IN_RISK_SET` (purchased ≥ c),
  `EVENT_RECORDED` (purchase ≤ delivery < c, status not X), `RECORD_STATUS_CONFLICT` (delivery record before c
  but final status canceled — a retrospective QA flag, not evidence that the cancellation was known at c), `UNRESOLVED_AT_CUT` (in the risk set, no valid record before c).
  UNRESOLVED is **not** "still in transit": it mixes in-transit, later-cancelled and never-recorded orders.
- Guards for any survival data set built at c: purchase < c for every row in the risk set; event time < c;
  duration > 0; follow-up > 0 (`as_of_violations`, run at every cut in the audit).

## 3. What the data show

Final-file categories, 31-day stale threshold (days past the promised deadline at the observation end):

| Category | Primary end (09-04 00:00) | Midnight end (09-03 00:00) |
|---|---:|---:|
| EVENT | 96,470 | 96,470 |
| RECENT_U_CANDIDATE | 123 | 127 |
| U_STALE_MISSING_OUTCOME | 1,606 | 1,601 |
| DELIVERED_TIME_MISSING | 8 | 8 |
| CANCELED_OR_UNAVAILABLE | 1,234 | 1,234 |
| PURCHASED_AT_OR_AFTER_OBSERVATION_END (U) | 0 | 1 |

- **Recent U are candidates only.** "At most 31 days past promise" is a screening rule; the file has no
  last-tracking time, so nothing shows these orders were observed until the cut. With the midnight end, one
  candidate (purchased 2018-09-03 09:06:57) is not even in the risk set (its follow-up would be −0.38 days);
  under the primary end its follow-up is +0.62 days. Thresholds 60 / 72 days give 177 / 193 candidates.
- **Most U are far past their promise**: median 251 days (shipped 210, invoiced 272, processing 322).
  Their observation mechanism cannot be verified from the file, so they are treated as missing outcomes,
  not as ordinary right censoring. (This does not prove the censoring is informative; it means it cannot be checked.)
- **Deliveries after the observation end.** 37 A/L deliveries are recorded at/after the primary end (53 at/after
  midnight); **6 of them are in the approved window under either convention.** As of the observation end these
  6 are unresolved and would be censored there. The earlier statement "no boundary censoring inside the window"
  held only for the final-file classification and is withdrawn.
- **Record–status conflicts.** 6 canceled orders carry a valid delivery date (5 in 2016, 1 purchased 2018-02-19 and
  delivered 2018-03-21, inside the window). They are isolated as `RECORD_STATUS_CONFLICT`, not counted as open or
  as events; listed in `record_status_conflicts.csv`.
- X: 625 canceled (75 had reached the carrier) and 609 unavailable. **No cancellation timestamp.**

### Unresolved orders at fold cut-offs (window, single seller; record-date rule)

| T | In risk set | Event recorded before T | Conflict | Unresolved at T | Deadline passed at T | Later final A / L / U / X | Later U or X |
|---|---:|---:|---:|---:|---:|---|---:|
| 2018-01-01 | 43,875 | 40,250 | 0 | 3,625 | 1,390 | 1,791 / 688 / 943 / 203 | 31.6% |
| 2018-04-01 | 64,734 | 59,299 | 1 | 5,434 | 2,121 | 2,311 / 1,503 / 1,295 / 325 | 29.8% |
| 2018-05-01 | 71,538 | 67,022 | 1 | 4,515 | 1,898 | 2,289 / 472 / 1,414 / 340 | 38.8% |
| 2018-06-01 | 78,272 | 74,023 | 1 | 4,248 | 1,974 | 1,897 / 493 / 1,498 / 360 | 43.7% |

"Later final" uses the final file and is shown only to describe the unresolved set; it is not information available at T.

## 4. The estimand depends on the final file unless the target is redefined

| | E_A — late among orders with an eventual valid delivery record | E_B — no delivery by the deadline |
|---|---|---|
| Target | P(delivery ≥ d \| final A/L): the stage-3/5 population | Must first decide: **no delivery record** vs **no actual delivery** (they differ whenever records are missing) |
| Fit at T | Censoring at T for unresolved orders that will end A/L → selecting them uses the future | All unresolved orders censored at T; no final-status filter |
| Evaluation | The common 19,950-order A/L test cohort: no censoring **under final-file retrospective evaluation**, so no IPCW needed (5 of these deliveries fall after the primary observation end and would be censored in an observation-end evaluation) | Must be on an E_B population (all in-risk orders whose deadline lies within follow-up), with stale U and conflicts handled per the record-vs-actual choice. The A/L cohort supports only a **conditional ranking comparison**; Brier/calibration there says nothing about E_B probabilities for all orders |
| Model shape | S → 0 is plausible | S(∞) may stay above 0 (never delivered). A standard log-normal AFT has S → 0; at best a finite-horizon approximation, which would need its own check against KM at the deadlines used |
| What it can claim | A method experiment (administrative truncation in a post-hoc cohort); not deployable; does not solve U/X | Deployable target, but only after the record-vs-actual choice, a finite horizon and its own evaluation are fixed |

The stage-3/5 classifier also scores a final-A/L population, but its **fit** uses only labels known at T.

## 5. Evaluation assumptions

- **Common A/L cohort** (19,950 test orders, 850 late): every delivery time is in the final file, so under
  final-file retrospective evaluation AP, Brier and weekly top-10% need no censoring correction. In an evaluation
  truncated at the observation end, 5 of these orders (delivered after 2018-09-04 00:00) would have to be censored.
  The existing classifier results are retrospective and are not recomputed. It is a conditional comparison for any survival estimand.
- **IPCW** (scikit-survival) is needed only for metrics on censored data; it assumes censoring independent of
  delivery time given covariates and a horizon tau within follow-up. That assumption cannot be checked for stale U,
  so no IPCW metric should be computed on a cohort containing them.
- **Censoring at a fold cut-off** depends on purchase time. It is acceptable under conditional independent
  censoring given the covariates (including purchase time) and adequate follow-up support. Drift in late share
  (4.6% / 6.7% / 1.3% in Apr / May / Jun 2018) makes this harder to defend; it does not by itself prove it fails.
- **Splits** follow purchase time (stages 3 and 5); no random `train_test_split`.
- **Log-normal shape (descriptive)**: log delivery time across final-file events has skew −0.20, excess kurtosis 0.32,
  normal probability-plot r = 0.998. This is marginal only; a conditional model would need its own checks.

## 6. Options for the owner (no recommendation to start 6b)

| Option | Scope | Cost | What it adds |
|---|---|---|---|
| **O1 — stop here** | This review + tests are the stage-6 result | none | A documented identification finding: why the file cannot support a deployable survival estimand without extra assumptions |
| **O2 — E_A method experiment** | KM + one log-normal AFT on the A/L population, censoring at T, labelled "post-hoc cohort, not deployable"; compared with LR on the common cohort | small–medium | Shows administrative truncation handled correctly; must not be presented as solving U/X |
| **O3 — E_B redesign** | First fix: record vs actual; a finite horizon; an E_B evaluation population and missing-data sensitivity. Model choice after that (standard AFT not assumed) | larger; new design review | A deployable target, if the choices hold |

Updated decision table:

| # | Status |
|---|---|
| D1 Estimand | **Withdrawn as a recommendation.** Owner chooses O1 / O2 / O3 |
| D2 Stale threshold | 31 / 60 / 72 days as **screening and sensitivity** thresholds only; not evidence that censoring is valid |
| D3 Evaluation | Common A/L cohort = conditional comparison; an E_B model must be evaluated on an E_B population |
| D4 Models | KM + one AFT is a reasonable size, but only after D1; training, tuning and evaluation must match the chosen target |
| D5 Libraries | Kept: lifelines (MIT) only; scikit-survival (GPL-3.0) cited for concepts, no code copied, not a dependency |
| D6 Reporting | Kept: no promised improvement; a model that does not beat LR is reported as is |

## 7. Limits of this review

- All categories depend on an inferred observation date; a confirmed extraction time could move U orders
  between candidate and stale (window results change only through the 6 late-recorded deliveries).
- Without cancellation or status-change timestamps, competing-risk methods (cumulative incidence) cannot be applied.
- "Later final" counts use the final file and are descriptive only.
