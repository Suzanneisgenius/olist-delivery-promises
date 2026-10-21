# Changelog

Versions before 0.6.0 are described in `docs/manager_handoff.md`, the stage handoffs and `docs/REPRODUCIBILITY.md`.

## E1 documents v6 — 2026-10-21 (wording only)
- Summary reframed around whether a matched calibration and rounding procedure makes promised dates comparable; three
  points: same target, different coverage; same rounding, different effect on continuous vs whole-day bounds; cohort
  filtered on one comparator. Closing sentence on what the study examines.
- Section 3: table "Three meanings of 'coverage holds'" (k/n on C; marginal guarantee under exchangeability; empirical
  coverage on E). Supplement unchanged.

## E1 final — 2026-10-21 (documentation and checks only; E1 closed to further post-hoc analysis)
- Main report v6: summary reframed (matched procedure, unequal reliability); "three meanings of coverage" table;
  rounding up "adds less than a day"; pointer to the mathematical note. Supplement: contribution rows for the note and
  the notebook.
- New: mathematical note (en/zh, LaTeX sources), `notebooks/e1_by_hand.ipynb`, `scripts/e1_final_recheck.py`,
  `docs/E1_FINAL_FIXES_2026-10-21.md`.
- Front page: `README.md` shows the current version only; earlier reports in `documents/archive/`, the v0.6.3 pipeline
  README in `docs/archive/` (byte-identical to the copy in `release/MANIFEST.sha256`).

## E1 documents v5 — 2026-10-21 (fifth review; no new experiment, no registered result changed)
- Rounding text: untruncated identity vs one-day minimum; subtract-one "not coverage-preserving in general".
- `scripts/e1_rounding_rules.py` input guards (finite scalar shift, non-empty 1-d input, overflow, integer labels);
  17 new tests (45 in `tests/test_posthoc_rounding.py`); red/green in `outputs/e1/redgreen_rounding/`.
- Window sentence narrowed; HGB-linear gap stated at the four reported targets; missing brace fixed; contribution
  statement: AI review is not peer review; Chinese research note marked superseded.
- `docs/REPRODUCE_E1.md`: recipe B reads the saved freeze; per-recipe saved directories; erratum b; recipe B run end to
  end from raw CSVs (`outputs/e1/recipeB_acceptance/`).

## E1 documents v4 — 2026-10-21 (fourth review; no new experiment, no registered result changed)
- Neutral title "Integer-valued delivery promises: calibration, coverage and temporal shift"; HGB vs linear described
  as two frozen policies at different realised coverage; "fair" -> matched design; E window in the sample definition;
  B0 "replacement standard not met"; H2 "no comparison formed" (machine record kept).
- Rounding: round-down rule replaces the v3 "integer-aware shift" (= subtract one day, invalid at whole-number bounds);
  `scripts/e1_rounding_rules.py`, `tests/test_posthoc_rounding.py` (28 tests).
- `scripts/e1_posthoc_methods.py` -> `outputs/e1/posthoc_m4/`: rounding rules, achieved coverage, E sample flow,
  window comparison, leave-one-week-out. Docs: `E1_POSTHOC_METHODS_REVIEW.md`; E2a protocol drafted (not run).

## E1 documents v3 — 2026-10-21 (third review; no new experiment, no registered result changed)
- Professor version retitled "Sharper forecasts, longer promises: calibration transfer in delivery-date policies" and
  rebuilt around a days-vs-coverage figure; H2 reported as "not tested (registered as 'not supported')".
- Post-hoc sensitivities (`scripts/e1_posthoc_review3.py` -> `outputs/e1/posthoc_r3/`): matched coverage on E,
  integer-aware shift, evaluation window by month and April-May only, late rate of C by month.
- Agent package r3: claims C20-C24 recomputed independently from the per-order files; `verify_all.sh` preflight.

## 0.6.3 — 2026-10-15 (review follow-ups; no new experiment)
- `scripts/release_evidence.py` is now a release gate: it fails on a config-hash mismatch, failed or empty tests,
  any automated UAT case not PASS, a block marker under `outputs/`, or a missing log; owner cases are listed, never
  signed. New `scripts/make_release.sh` rebuilds everything and writes fresh `release/logs/` before the gate.
- Verdict key `tighter_at_similar_reliability` renamed `shorter_with_coverage_loss_within_tolerance` (label only).
  The registered config keeps its original wording ('tighter at similar reliability'); it is not edited after
  registration. The rule itself (≥ 1 day shorter, ≤ 1 point lower coverage) is unchanged.
- `nominal_arl_threshold` handles q = 1 (ARL = number of required weeks); `calibrate_h` refuses a target above the
  restricted-mean ceiling (cap + 1) and bounds its bracket search. Neither case occurs in the current configuration.
- Research-plan wording: "更紧且同样可靠" replaced by "更短，且覆盖率损失在预设容忍范围内"; the step-0 state paragraph no
  longer assigns causes ("配送慢 / 日期紧") from marginal medians; "尾部很薄" removed.
- Results vs 0.6.2 (`release/logs/compare_0.6.2_vs_0.6.3.json`, 96 output files): 79 byte-identical, including every
  stage-7 result table and the monitoring outputs. 17 differ: the renamed verdict key (`verdicts.json` and the
  stage-7 report, values identical), the UAT-12 gate-test count (23 → 25, new gate tests), run metadata, and
  last-digit float noise (~1e-13) in the stage-2 SQL cross-check.

## 0.6.2 — 2026-10-14 (release evidence and wording; no new experiment)
- Monitoring burden table split into one-week crossing probability, full alarm condition, exact ARL and assumption;
  the threshold rule's 2.2 × 10⁻⁸ is labelled as a one-week crossing probability, not the rule's alarm probability.
  The "~10¹³ times" comparison now states it is a ratio of long-run alarm frequencies (1/ARL).
- Conformal wording: the guarantee rests on exchangeable calibration and test scores; here that premise cannot be
  relied on, and over-coverage alone does not prove it is violated (reference added to `docs/REFERENCES.md`).
- 2018-10-17 described as the latest delivery record in this sample, not a follow-up cut-off; the evaluation is
  described as one out-of-time evaluation by design on data analysed many times, not a blind test.
- Next-step wording: simulated false-alarm budgets are estimates with Monte Carlo error, not exact values.
- Release evidence: `release/RELEASE.md`, `release/MANIFEST.sha256`, `release/logs/` (full run, pytest log and JUnit).
- Results vs 0.6.1 (`release/logs/compare_0.6.1_vs_0.6.2.json`, 96 output files): 81 byte-identical, including every
  stage-7 result table; 15 differ only in run metadata (timestamps, lineage, evidence hashes, the re-rendered
  monitoring report text) and last-digit floating-point noise (~1e-13) in the stage-2 SQL cross-check.

## 0.6.1 — 2026-10-14 (fixes after review; no new experiment)
- B0 quantile uses the empirical inverse CDF (`inverted_cdf`, the ⌈n·q⌉-th smallest value) as registered
  (I1: MA at 0.95 45 → 44 days; PE at the matched target 35 → 34 days; no verdict changes).
- Week finality = last purchase day (Sunday) + longest promise + 1 day (I2: every date and calendar delay 1 day earlier).
- ARL: simulated value labelled as a restricted mean with censored share; exact geometric ARL for h = 0 and exact
  threshold-rule ARL added (I3).
- `to_promise` refuses non-finite input; 1-day / 1-point edges use a 1e-9 tolerance (I4).
- A stage-7 test no longer retires the real monitoring report; the report is in the package again (I5).
- The CUSUM at h = 0 is named a single-week LLR rule; the claim that it is better than the threshold rule is
  withdrawn (deviation D1).
- Failure drills: the backup is deleted only after a byte-identical restore; unexpected success or a missing
  assertion fails the script; two tests on a disposable fake project.
- Per-order stage-7 evidence: `outputs/stage7/orders/evaluation_promises.csv`, `calibration_scores.csv`.

## 0.6.0 — 2026-10-14
- Stage 7 parts 1–3 (promised-date policies, calibration, monitoring), exploratory and pre-registered.
