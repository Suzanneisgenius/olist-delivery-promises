# Review brief for an agent: Olist E1 (promised delivery dates)

## 1. What this is
A sealed, pre-registered exploratory experiment ("E1") inside a student data-science portfolio project on the public
Olist e-commerce data. Question: **when does a lower forecast loss fail to give a better promised delivery date?**
Three policies were compared under one fixed protocol: a per-state quantile rule, linear quantile regression and a
shallow gradient-boosted model (HGB), each calibrated by a one-sided split-conformal-style shift.

The author led the project, developed the initial research design, and carried out multiple rounds of revisions.
Claude helped refine selected portions of the code; see `AUTHORSHIP.md` for the confirmed scope. The project went
through ten earlier review rounds (see PRIOR_REVIEWS.md). Every change to the plan is logged with time and reason
in `docs/E1_DECISIONS.md`.

## 2. Your task
Give an independent, critical review. Report only what you can support with evidence from this package.
Priorities, highest first:

1. **Claims vs evidence.** Does every claim in `AGENT_REVIEW/claims.json` and in the professor version
   (`AGENT_REVIEW/documents/E1_main_report.txt` + `E1_supplement.txt` + `E1_math_note_en.txt`; v2-v5 texts are kept in `superseded_v2/`-`superseded_v4/`; `research_note_zh` is an old interpretation, see `AGENT_REVIEW/documents/README.md`) follow from the saved outputs?
   Look for over-claiming (causal language, "faster delivery", "confirmed advantage", untouched-test-set language).
2. **Time ordering and leakage.** Labels used only if delivered before each decision date; seller-history features
   built only from orders delivered before the snapshot; selection on F0 -> V only; calibration on C only; E used only
   in the final scoring run. Code: `src/olist_analytics/e1_data.py`, `features.py`, `e1_pipeline.py`.
3. **Freeze integrity.** `src/olist_analytics/e1_freeze.py`, `run_score()` in `e1_pipeline.py`; tests in
   `tests/test_e1_final.py`. Distinguish the historical guarantees (scoring-time code in `snapshots/src_at_e1_scoring/`)
   from the post-hoc hardening (current `src/`, labelled as retrospective).
4. **Statistical interpretation.** Calibration without exchangeability; week-block bootstrap with 17 clusters;
   selection on the same V; H1 as fixed-order design sensitivity; H2's g = 0 by construction (C* = C0 = B3).
5. **Reproducibility.** `docs/REPRODUCE_E1.md` (corrected 2026-10-21; the erratum to the sealed v2 archive is `docs/REPRODUCE_E1_ERRATUM_2026-10-21.md`): are recipes A, B, C executable and correctly separated?
6. **Presentation.** Readability of the professor version for a statistics / data-science faculty reader.

**New in r3 (after the third external review, 2026-10-21).** The professor version was rewritten around
calibration transfer (HGB is shorter at equal coverage; its registered promise was longer because the C shift carried
it further). Four post-hoc sensitivities were added: matched-coverage curves on E, an integer-aware shift, the
evaluation-window filter on Olist's estimated week, and the seasonality of C (`scripts/e1_posthoc_review3.py`,
`outputs/e1/posthoc_r3/`, claims C20-C24). They choose no policy and change no registered verdict; please check that
the documents never present them as if they did. `verify_all.sh` now fails early (exit 2) if pytest, duckdb or the
numeric stack is missing.

**New in r6 (final; E1 closed to further post-hoc analysis).** Mathematical note (k/n vs k/(n+1) vs evaluation
coverage; quantile optimality; whole-day rounding), `notebooks/e1_by_hand.ipynb` (recomputes a registered result, no
new analysis), main report v6 wording, contribution rows, a front page (`README.md`) with only the current version.
Targeted re-verification: `python3 scripts/e1_final_recheck.py` (step 10 of verify_all; record in
`docs/E1_FINAL_FIXES_2026-10-21.md`).

**New in r5 (fifth review).** (1) The rounding argument now separates the untruncated identity (Y <= U iff
Y <= floor(U)) from the one-day minimum, which can only enlarge the event; subtract-one is described as not
coverage-preserving in general rather than always under-covering (claims C25, C29; 17 new tests). (2) The rounding
helper refuses non-finite or non-scalar shifts, empty / 2-d input, overflow and non-integer labels (red/green in
`outputs/e1/redgreen_rounding/`). (3) Main-text window sentence narrowed; the HGB-linear gap is stated at the four
reported targets. (4) `docs/REPRODUCE_E1.md` recipe B read FREEZE.json after it had been moved; fixed (per-recipe
saved directories), with an end-to-end acceptance run from raw CSVs in `outputs/e1/recipeB_acceptance/`
(erratum `docs/REPRODUCE_E1_ERRATUM_2026-10-21b.md`).

**New in r4 (fourth review, methodological).** Neutral title ("Integer-valued delivery promises: calibration,
coverage and temporal shift"). The v3 "integer-aware shift" was the subtract-one rule max(1, ceil(U - 1)), which fails
when U is a whole number; it is replaced by round-down max(1, floor(U)), which keeps the coverage event of the
continuous bound for whole-number Y (`scripts/e1_rounding_rules.py`, `tests/test_posthoc_rounding.py`). Added: achieved
coverage in matched comparisons; frozen points vs E-tuned diagnostic curves in the main figure; the E sample flow by
month (`outputs/e1/posthoc_m4/e_sample_flow.csv`, built from the order mart, which is not shipped); leave-one-week-out.
Claims C22 (rewritten), C25-C28. Please check in particular: (a) the round-down argument and its tolerance handling;
(b) that the documents never present diagnostic curves or post-hoc rules as registered results; (c) the E2a draft
(`docs/E2A_PROTOCOL_DRAFT.md`, `config/e2a_sim_draft.yaml`): it is NOT registered and NOT run.

## 3. Ground rules
- Read-only with respect to the evidence. Work in a copy of this folder.
- Do not re-score E with modified code, tune anything on E, or edit `outputs/e1/freeze/FREEZE.json`.
- Do not disable the code-fingerprint check to make the historical freeze run with the current code.
- Raw Olist CSVs and order-level marts are NOT included. Everything in section 4 runs without them. A full rebuild
  (recipes B / C in `docs/REPRODUCE_E1.md`) needs the public Kaggle data and is optional.
- Recorded environment: Python 3.13.16, Linux x86_64; numpy 2.5.3, pandas 3.0.5, scikit-learn 1.9.1, scipy 1.18.1
  (`requirements-e1-tested.txt`). Note your own environment if it differs.

## 4. Quick start (about one minute)
```
cd olist-e1-agent-review
pip install -r requirements-e1-tested.txt     # if needed
bash AGENT_REVIEW/verify_all.sh                 # expected: 11 x PASS, "ALL CHECKS PASSED"
```
It checks: package manifest; config and freeze hashes; the scoring-time source fingerprint against the freeze; the
post-hoc addendum's binding to the freeze; the full test suite (362); recomputation of every E1 number and every
supplementary number from saved per-order files (numpy / pandas only); every quantitative claim in `claims.json`;
the targeted re-verification; and the harness itself (`AGENT_REVIEW/harness_tests/`: missing PDF tools, unreadable
PDFs, two runs in a row). Step 10 reads the PDFs with pdftotext or pypdf; with neither it is SKIP, not PASS, and the
last line says "PASSED WITH SKIPS". Everything it writes goes to `AGENT_REVIEW/verify_output/`.
Passing means the saved outputs are internally consistent. It is not a raw-data-to-model reproduction.

## 5. Where things are
| Path | Content |
|---|---|
| `AGENT_REVIEW/claims.json` | 19 claims: statement, values, tolerance, evidence file, where stated |
| `AGENT_REVIEW/documents/` | professor version + supplement (PDF and text), Chinese research note and plan (PDF and text) |
| `config/date_model_e1.yaml`, `outputs/e1/PREREGISTRATION_SHA256.txt` | pre-registration (v3) and its hash history |
| `docs/E1_DECISIONS.md` | decision log, every change with time, reason, whether a new E result had been seen |
| `outputs/e1/prep/` | sample tables, partition manifest with id hashes, B2 reproduction of stage 7 |
| `outputs/e1/select/`, `select_repro1/` | selection on V (original run; reproduction run with per-order V predictions) |
| `outputs/e1/final/`, `freeze/`, `models/` | fit on F, shifts on C, freeze record, fitted models, post-hoc input-identity addendum |
| `outputs/e1/score/` | final E1 scoring: results.json, policy / monthly / group tables, per-order promises, bootstrap draws |
| `outputs/e1/posthoc/`, `sim/`, `sim_paired/` | post-hoc V checks, synthetic calibration simulation (two runs) |
| `outputs/e1/redgreen*/` | before/after test logs for each fix, with the paths and hashes of the code tested |
| `scripts/e1_verify_*.py` | independent recomputation scripts |
| `snapshots/src_at_e1_scoring/` | the exact source that produced the reported results |

## 6. Known limitations (already disclosed; report them only if you find something beyond what is stated)
- One evaluation period, examined earlier in Stage 7: pre-registered exploratory, not a blind test.
- Conditional population: single-seller orders that were eventually delivered.
- Over-coverage on E is not explained; delivery times, original estimated dates and order mix are not separated.
- No independent full rebuild from raw data has been done; hashes and logs cannot prove no unrecorded runs.
- Input-content hashing was added after scoring (addendum); it is not evidence that such checks existed earlier.
- The old contribution draft in the historical review copy is superseded by `AUTHORSHIP.md` and part B of
  `documents/current/E1_supplement.pdf`. It is not the current account of the author's contribution.

## 7. What to return
Use `AGENT_REVIEW/REPORT_TEMPLATE.md`. For each finding: severity, location (file and line or section), what is wrong,
evidence (a command or a number you computed), suggested fix, and your confidence. Say explicitly what you did not check.
