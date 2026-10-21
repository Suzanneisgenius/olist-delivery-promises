# Stage 1 review (2026-10-12) — response, rev. 1.1

| Review item | Severity | Change | Evidence |
|---|---|---|---|
| Report written even when a reconciliation fails | P1 | `release_gate()` runs after all blocking checks and before the report; on failure it writes `qa/RELEASE_BLOCKED.json`, deletes any previous report, exits non-zero | `tests/test_release_gate.py`; live run with one SQL cell flipped → exit 1, no report |
| "Effective data end" stated as fact | P1 | Renamed **inferred observation boundary**; report states it is not a confirmed extraction date and shows the 37 later deliveries | report §9; `cohort.py` docstring |
| U cause stated as "status never updated" | P1 | Wording: long-unconfirmed, cause not identifiable; share now uses `order_estimated_delivery_date` (96.6%), not the week start | report §9; `run_stage1.py` |
| "1,359 orders stay in OTD" | P1 (summary wording) | Report gives the split: A 1,326, L 24, U 9 → 1,350 OTD-eligible orders are not removed | report §5 |
| `proposed_in_window` vs longest run could disagree | P2 | Split into `passes_weekly_guards` and `in_selected_window`; weekly calendar completed first so a missing week breaks a run; summaries use the selected window only | `tests/test_cohort.py::test_missing_week_breaks_the_run_and_flags_stay_separate` |
| 200-order guard used all orders | P2 | Guard is now A+L ≥ 200 (`min_eligible_orders_per_week`); window unchanged | `test_min_eligible_uses_a_plus_l_not_all_orders` |
| No FK orders.customer_id → customers | P2 | Added to contract; missing customer kept as state `UNKNOWN` and reason code `missing_customer_record`; blocking check: state totals = OTD-eligible total | `test_orders_customer_foreign_key_is_checked`, `test_missing_customer_kept_as_unknown_state` |
| NO_ESTIMATE silently dropped by groupby | P2 | Bucket `NO_VALID_ESTIMATE` counted as unassigned; blocking check weekly + unassigned = mart rows | `test_weekly_totals_plus_unassigned_equal_mart` |
| Estimated date before purchase still labelled | P2 | New rule → `NO_VALID_ESTIMATE` + reason code `estimated_before_purchase` (0 in this file) | `test_estimate_before_purchase_is_not_labelled` |
| Empty / no-late / no-window edge cases | P2 | Explicit `NO_QUALIFYING_WINDOW`, horizon `None`, NaN (not 0) for zero denominators; no int-of-NaN | `tests/test_cohort.py` (4 tests) |
| "outside Brazil" | P2 | "outside the configured bounding box (a rectangle, not a national border)" | report §8 |
| `source_row_id` called a line number | P2 | Renamed `source_record_no` (1-based record number) and documented | `io.py`, report §1 |
| Sensitivity 31/45/60 days | — | Computed by the pipeline: 74 / 72 / 70 weeks, 92.92% / 92.65% / 92.46%; 98% coverage → 39 passing weeks, longest run 7 | `qa/window_sensitivity.csv`, report §9 |
| Centred decomposition | approved | Full spec incl. centred entry/exit recorded for stage 2 | `docs/metric_dictionary.md` |
| Environment versions | note | Recorded in `qa/stage1_facts.json` and report §1 | — |
| pandas FutureWarning | note | Removed `fillna(False).astype(bool)` on object columns; suite passes with `-W error::FutureWarning` on pandas 3.0.5 (not re-tested on 2.3.3) | — |

Unchanged on purpose: orders_mart logic and all headline numbers (A/L/U/X, 6.77%, 1,373, 92.92%) — the review reproduced them.
Not done: human sign-off of the 20-order sample (columns left empty for the reviewer).

# Stage 1.1 re-check (2026-10-12) — response, rev. 1.2

| Item | Change | Evidence |
|---|---|---|
| P1 early contract failure left the old passing report | Whole-run lifecycle in `gate.py`: the current report is retired to `outputs/history/SUPERSEDED_*` at run start; contract failures go through `release_gate`; any other exception also writes `RELEASE_BLOCKED.json`. A stage-1 rerun also retires the stage-2 report. | `test_hard_contract_failure_leaves_no_current_passing_report`, `test_unexpected_error_is_also_a_blocked_release` |
| P1 no window still "Approved for stage 2" | Audit pass and comparison readiness are separate. Readiness is READY only if a window exists and equals `config/approvals.yaml`; otherwise NOT_READY / NEEDS_RE_APPROVAL. No hard-coded approval text. Stage 2 refuses to run unless READY. | `test_no_window_is_never_ready`, `test_window_different_from_approval_needs_re_approval`, `tests/test_stage2_gate.py` |
| P2 independent checker used the old estimate rule | `classify_raw_order()` (stdlib only) checks missing / before-purchase estimate first; `days_late` is undefined on an invalid estimate in both the checker and the mart. | `test_classifier_matches_mart_rule_order`, `test_estimate_before_purchase_is_not_labelled` |
| Record number wording | "Loaded source tables keep `source_record_no`; the mart traces back by `order_id`." | report §1 |
| Centring wording | Report §11 now quotes the dictionary: performance = w̄ × Δp; mix, entry, exit against c; only the overall identity is fixed when states enter/exit. | report §11 |
| U comment / sample wording | `assumptions.yaml` comment aligned; sample "covers the listed typical cases". | — |

Version note: tests pass on Python 3.13.16 / pandas 3.0.5 with `-W error::FutureWarning`. The reviewer's
pandas 2.3.3 DeprecationWarnings were not reproduced here and are not claimed fixed.
