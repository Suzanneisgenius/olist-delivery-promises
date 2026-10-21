# Promised delivery dates on Olist: when is a matched comparison still unequal?

A pre-registered study on public Olist e-commerce orders (Brazil, 2017–2018). It compares a per-state quantile rule, a
linear quantile regression and a shallow gradient-boosted model (HGB) as ways to set a whole-day promised delivery date
with 90% target coverage.

> Public-data portfolio project. Not affiliated with Olist. The evaluation orders had been examined earlier in the
> project, so this is pre-registered exploratory work, not a blind test.

![Frozen policies and diagnostic curves on the evaluation period](documents/current/fig_days_vs_coverage_E.png)

*Filled squares: policies calibrated on Oct–Dec 2017 only, frozen, scored once on Apr–Jul 2018. Dashed lines: post-hoc
diagnostic curves that use the evaluation outcomes; not deployable, not used to choose a model.*

## Three answers

*[Author: these are drafts. Rewrite them in your own words before sharing.]*

| Question | Answer |
|---|---|
| What did I expect at first? | That a model with lower forecast loss would give shorter promised dates at the same reliability, and that a regression would beat a simple per-state rule. |
| Which result changed my mind? | Matching the comparison reversed the regression-versus-rule result (+2.57 → −1.54 days). Also, HGB had lower loss, yet its frozen policy promised 1.22 more days: it reached 97.1% coverage against 96.2%, so the two points were not at the same reliability. |
| What do I still not know? | Why every calibrated policy over-covers the evaluation period (96–97% for a 90% target): changing delivery times, the cohort filter on Olist's estimated date, or order mix. I also don't know whether rounding down or recalibration would hold up in a new period, or how the results extend beyond single-seller delivered orders. |

## Current version: start here

| File | What it is |
|---|---|
| [`documents/current/E1_main_report.pdf`](documents/current/E1_main_report.pdf) | Main report (7 pages): question, design, results, limits |
| [`documents/current/E1_math_note_en.pdf`](documents/current/E1_math_note_en.pdf) ([中文](documents/current/E1_math_note_zh.pdf)) | Mathematical note (3 pages): why a quantile; what k/n, k/(n+1) and evaluation coverage each show; whole-day rounding |
| [`notebooks/e1_by_hand.ipynb`](notebooks/e1_by_hand.ipynb) | Four small checks by hand: loss enumeration, hand calibration, rounding cases, one recomputed result |
| [`documents/current/E1_supplement.pdf`](documents/current/E1_supplement.pdf) | Model selection, simulation, post-hoc sensitivity tables, integrity record, contribution statement |

### Run the checks (no raw data needed)

```bash
pip install -r requirements-e1-tested.txt
bash AGENT_REVIEW/verify_all.sh        # 10 checks, about a minute: hashes, 362 tests, every reported number
pip install notebook && cd notebooks && jupyter notebook e1_by_hand.ipynb   # optional
```
Rerunning the whole study from the raw Kaggle CSVs: `docs/REPRODUCE_E1.md`.

### Reading paths

**Statistics faculty:** research question (main report §1) → main figure (§4) → mathematical note → limits (§6) →
contribution statement (supplement, part B).

**Data science / analytics recruiters:**

| Step | Where |
|---|---|
| Business problem: a promised date trades off late orders against waiting time | main report §1–2 |
| Data contract and quality checks | `config/data_contract.yaml`, `outputs/stage1_quality_report.md` |
| Time-safe modelling: labels used only once delivered; frozen before evaluation | main report §3, `docs/E1_DECISIONS.md` |
| Decision meaning: days promised against coverage | main report §4–5 |
| Reproducible delivery: one-command checks, end-to-end rerun from raw CSVs | `docs/REPRODUCE_E1.md`, `outputs/e1/recipeB_acceptance/` |

## Appendix: process and integrity

These records show how the work was checked. They are not research results.

- **Registered state.** Config v3 SHA-256 `ae6a4a46…20152`. Freeze record `outputs/e1/freeze/FREEZE.json`, SHA-256
  `3b62af1a…328dd`, unchanged since it was written. Scoring-time code is in `snapshots/src_at_e1_scoring/`.
- **Checks.** 362 automated tests pass. Every reported number is recomputed independently. The reproduction recipes B
  (historical code) and C (current code) were run end to end from raw CSVs and matched the saved results.
- **Change log and reviews.** Every plan change is in `docs/E1_DECISIONS.md`. Post-hoc analyses are in
  `docs/E1_POSTHOC_METHODS_REVIEW.md` and the final fixes in `docs/E1_FINAL_FIXES_2026-10-21.md`. Earlier review
  rounds are summarised in `AGENT_REVIEW/PRIOR_REVIEWS.md` (review package).
- **Not done.** A second evaluation period. A cohort that does not depend on Olist's estimated date. The E2a methods
  study (`docs/E2A_PROTOCOL_DRAFT.md`) is drafted, not registered and not run.
- **Archive.** Earlier report versions are in `documents/archive/`. The full pipeline README for stages 1–7
  (v0.6.3, byte-identical to the copy listed in `release/MANIFEST.sha256`) is
  `docs/archive/README_pipeline_v0.6.3.md`.
