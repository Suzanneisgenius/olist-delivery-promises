# Changelog

Versions before 0.6.0 are described in `docs/manager_handoff.md`, the stage handoffs and `docs/REPRODUCIBILITY.md`.

## Dashboard publication copy — 2026-10-28
- Lead the dashboard, mathematical explanation and repository introduction with the research decisions and findings.
- Consolidate repeated disclaimers while retaining cohort definitions, exploratory status, post-hoc labels and theorem assumptions.
- Correct the table 4 equality condition: distinct residuals ensure equality; ties can make coverage conservative.
- Populate the dashboard contribution panel from the author-confirmed statement and streamline that statement's revision history.
- Preserve all saved data, model code, sealed documents and E1 results.

## Diagnostics page: review corrections and notebook styling — 2026-10-28 (no result changed)
- Table 4 now labels its first two rows as bounds for the real-valued bound (at least k/n on the calibration set; at
  least k/(n+1) for a new order, with equality for almost surely distinct residuals) and its observed rows as the registered rounded-up
  promise.
- The weighted-calibration passage states the covariate-shift assumptions and no longer reads as an impossibility
  result: if P(Y|X) changes, the guarantee does not apply and weighting by X is not guaranteed to restore coverage. It
  notes that classifier odds estimate the likelihood ratio up to a constant that the weights' normalisation cancels.
  This passage and the coverage bounds without exchangeability move into a fold, "Going further", with Fig. 8.
- Links to a step (#m1 to #m4) keep their address after the page opens, on reload and when shared.
- The footer and page README say that views 01 to 03 use saved outputs and view 04 adds illustrative calculations and
  seeded simulations. Step 1 states that the costs are positive and that Y is a nonnegative integer.
- Notebook styling: a hand-written face (Kalam) and a violet pen with a highlighter for view numbers, margin labels,
  one boxed key result per step and short suggestions beside the demonstrations; demonstrations on dotted paper; a
  short fade between views, off under reduced motion. Chart colours are unchanged.

## Diagnostics page: view 04, the mathematics — 2026-10-27 (no result changed)
- New view 04 sets out the argument behind the promised-dates comparison in four steps (quantile, calibration, whole
  days, why calibrating well is not future reliability), each with a small demonstration on illustrative numbers.
- Step 4 applies coverage bounds without exchangeability (Barber et al., 2023, Theorems 2a and 3) and weighted
  calibration under covariate shift (Tibshirani et al., 2019, Corollary 1), with a toy simulation; the Beta
  distribution of calibration-conditional coverage is a collapsed supplement. No new analysis of E1.
- The view switcher is numbered 01 to 04 and the opening lists the new view; the promised-dates view points to it in
  place of its short mathematics band. Formulas use KaTeX 0.16.11 from jsDelivr.

## Diagnostics page: layout, mathematics, contribution panel — 2026-10-27 (no result changed)
- New layout: one typeface (Atkinson Hyperlegible Next), ink on paper with colour kept for the data. The opening lists
  the three findings, each opening its view; the view switcher stays at the top. Every number, label and sentence of
  the previous page is kept: the opening's three sentences become the three findings.
- The promised-dates view ends with the three results it rests on, linked to the mathematical note and the notebook.
- An empty "My contribution" panel, hidden until the author writes it.
- The data files, `aggregate.py` and the Pages workflow are unchanged.

## Diagnostics page and wording, after the v5 review — 2026-10-27 (no result changed)
- Table 3 shows the coverage each policy actually reached beside its mean days and is labelled as days at the first
  shift reaching each coverage level; whole-day steps make policies overshoot (state rule 90.75% at the 90% level).
- The recalibration note no longer treats a 30-day lag as making labels complete, or the visible direction of the
  error as a reason a test would show little.
- README and the wording-corrections note (A2, A6, Part C) describe what the verifier checks: the 26 numerical claims
  marked `auto`, some against saved aggregates; the pinball comparisons are of whole-day, unshifted promises.

## Verification from a symlinked path — 2026-10-27 (checks only; no result changed)
- `AGENT_REVIEW/verify_all.sh` changes to the physical directory (`cd -P`) before setting `PYTHONPATH`. Started from a
  path through a symlink (on macOS `/tmp` is one), the entry-module provenance checks in `tests/test_e1_final.py`
  compared unresolved module paths with the resolved package path and step 06 failed (1 failed, 19 errors; review
  2026-10-27). `src/` is unchanged.
- New harness test `test_runs_from_a_symlinked_path` (step 11, now 7 tests): fails with the old script, passes with
  the new one.

## E1 wording corrections — 2026-10-27 (post-seal note; no result, freeze record or sealed PDF changed)
- New: `docs/E1_WORDING_CORRECTIONS_2026-10-27.md`. Part A corrects the wording of existing conclusions (H3 under the
  registered rounding rule, the loss comparison, what "frozen" covers, the k/n identity, the bootstrap name, the scope
  of independent recomputation); Part B records audit findings without effect sizes (final-status filter with 6
  candidate records, recipe B input); Part C lists the diagnostics-page corrections made before publication.
- Linked from README and the diagnostics page; README's recomputation claim narrowed to `claims.json`; decision-log
  entry added.

## Diagnostics page on GitHub Pages — 2026-10-27 (publishing only; no result changed)
- New: `.github/workflows/pages.yml` publishes `docs/diagnostics_page/index.html` and `data/` to GitHub Pages after
  rebuilding the data with `aggregate.py` and comparing it with the committed files. Needs Settings > Pages > Source:
  GitHub Actions.

## Diagnostics page — 2026-10-27 (reading aid; aggregates of saved outputs; no result changed)
- New: `docs/diagnostics_page/`. `aggregate.py` (standard library only, read-only) rebuilds seven aggregate tables
  from saved stage-3, stage-5 and E1 outputs and checks them against the saved stage-5 fold metrics and the stage-3
  top-10% picks and calibration bins. Weekly picks follow each stage's own rule (the stage-3 test set by purchase week,
  each stage-5 fold by purchase week), and the random baseline uses the same weekly budgets. `check_budget.py`
  rechecks every budget row with `modeling.top_share_by_week`.
- `index.html` is a standalone three-view page (weekly picks, probability reliability, promised dates) that reads
  `data/`. No order-level data and no recalibration; E1 numbers are copied, not recomputed.

## E2b protocol draft — 2026-10-26 (draft only; not registered, not run; no E1 file changed)
- New: `docs/E2B_PROTOCOL_DRAFT.md` and `config/e2b_features_draft.yaml`. One pre-specified group of two
  destination-history features for E1's selected HGB setting (D3), motivated by E1's V residual flag;
  hyperparameters held fixed; adopted only if V loss is at least 1% lower. Whether the optional second look at E
  (Q3) is included is left to the author at registration.
- E1's response to the residual flag (`features_added: none`) still has no entry in `docs/E1_DECISIONS.md`; that
  belongs to the E1 wording revision, not to this draft.

## Verification harness — 2026-10-25 (checks only; no result changed)
- `verify_all.sh` reports PASS, FAIL or SKIP per step and says "PASSED WITH SKIPS (n)" instead of "ALL CHECKS
  PASSED" when a check could not run; `--strict` turns a SKIP into a failure; steps can be run by name.
- Step 10 (`scripts/e1_final_recheck.py`): without pdftotext it reads the PDFs with pypdf, and with neither it is
  SKIP instead of a silent pass; an unreadable PDF is a FAIL. It no longer rewrites the sealed
  `outputs/e1/final_recheck/recheck.json`.
- Steps 07 and 08 write their recomputations to `AGENT_REVIEW/verify_output/` and compare them with the saved copies
  in `outputs/e1/` instead of rewriting those.
- New step 11: `AGENT_REVIEW/harness_tests/` (missing PDF tools, unreadable PDFs, two runs in a row, saved copy
  compared). Kept outside `tests/`, so the registered suite is still 362 tests.

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
