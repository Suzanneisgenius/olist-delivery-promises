# Olist Delivery Performance & Late-Delivery Risk

Independent offline analysis on the public Olist e-commerce dataset (2016–2018):
weekly delivery performance by customer state, stage-timing diagnosis, and a
purchase-time late-delivery risk model. **Status: v0.6.3 — stages 1–4 complete with a fail-closed release gate (v0.4.1); stage 5 rolling backtest published with limits; stage 6a feasibility review revised (rev. 2); stage 6b not started — the owner must first choose the estimand (O1 stop / O2 E_A method experiment / O3 E_B redesign). Stage 7 (exploratory, pre-registered): promised-date policies and monitoring — the simple per-state rule was kept over the regression; see `docs/STAGE7_DATE_POLICY.md`. Owner review of the 20-order sample and final business sign-off are still open.**

> Public-data portfolio project. Not affiliated with Olist. Not related to any internship work.
> Olist has no carrier IDs: sellers are not carriers, and the estimated delivery date is not an SLA.

## Run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e .                 # or the exact tested versions: pip install -r requirements-tested.txt
# put the 9 Olist CSVs in data/raw/ (not committed)
export PYTHONPATH=src            # needed only if you did not run `pip install -e .`
python -m olist_analytics.run_all
#   = stage 1 → 2 → 3 → independent verification (scripts/verify_stage3.py, isolated) → 4 → 5 → 7 → 7 part 3;
#     stops at the first failure (~5 min)
pip install playwright && playwright install chromium   # optional, browser checks only
python scripts/ui_check_stage4.py                       # browser checks on the current pages
python scripts/build_uat.py      # outputs/stage4/UAT.md; fails if any test fails or evidence is stale
python -m olist_analytics.survival_audit                # stage 6a feasibility tables (no model fitted)
python -m pytest -q
```
Reproducibility check (two fresh environments, timings, failure drills): `docs/REPRODUCIBILITY.md`.
Release evidence for this package (full-run log, pytest log, SHA-256 manifest): `release/`; changes: `CHANGELOG.md`.
To make a release with fresh logs: `scripts/make_release.sh <version>` — deletes `release/`, reruns the whole pipeline,
browser checks, pytest and UAT into `release/logs/`, then runs the gate (`scripts/release_evidence.py`), which exits
non-zero if the config hash, tests, any automated UAT case, a block marker or a required log fails. It never signs
UAT-13/14; a gate PASS is not owner acceptance.
Single stages: `python -m olist_analytics.run_stage1` … `run_stage5`, `run_stage7`, `run_stage7_monitor` (each checks its own entry conditions).
Each stage retires its current report at start and publishes a new one only if every blocking check passes;
otherwise it writes a stage-specific block marker and exits non-zero. Stage 1 uses
`outputs/qa/RELEASE_BLOCKED.json`; stage 2 uses `outputs/stage2/qa/RELEASE_BLOCKED.json`.
Old reports and review pages are retained as explicitly superseded history. Stage 2
checks the raw-file hashes against the Stage 1 release before calculating.
Outputs: `outputs/stage1_quality_report.md`, `outputs/qa/*.csv`, `outputs/marts/orders_mart.csv` (git-ignored).

## Layout
| Path | What |
|---|---|
| `config/data_contract.yaml` | keys, required fields, types, foreign keys per table |
| `config/assumptions.yaml` | time zone, on-time rule, geo box, window-proposal thresholds |
| `src/olist_analytics/` | stage 1: `io`, `contract`, `mart`, `cohort`, `report`, `run_stage1` · stage 2: `weekly`, `decompose`, `report2`, `dashboard`, `run_stage2` · stage 3: `features`, `modeling`, `report3`, `run_stage3` · stage 4: `site`, `run_stage4` · stage 5: `run_stage5` · stage 6a: `survival_audit` · stage 7: `date_policy`, `run_stage7`, `monitoring`, `run_stage7_monitor` · shared: `gate`, `run_all` |
| `config/backtest.yaml` | stage-5 cut-offs and rules |
| `config/date_policy.yaml` | stage-7 pre-registration (SHA-256 in `outputs/stage7/PREREGISTRATION_SHA256.txt`; changes in `docs/DATE_POLICY_DECISIONS.md`) |
| `scripts/` | `verify_stage3.py` (independent, no project imports), `ui_check_stage4.py`, `build_uat.py` |
| `uat/owner_signoff.csv` | owner sign-off, bound to a release hash; never written by code |
| `config/model.yaml` | stage-3 design: population, splits, label rule, feature whitelist, grids |
| `config/approvals.yaml` | owner decisions on record; a computed window that differs needs re-approval |
| `sql/` | independent DuckDB re-implementations used as cross-checks |
| `docs/` | metric dictionary, STTM, model card, refresh checklist, manager handoff, stage handoffs, `STAGE6A_SURVIVAL_FEASIBILITY.md`, `REFERENCES.md`, `explainers/` (one card per stage) |
| `tests/` | hand-computed fixtures (no synthetic analysis data) |

## Plan
| Stage | Scope | Status |
|---|---|---|
| 1 | contract, quality audit, orders_mart, KPI definitions | accepted with conditions; rev. 1.2 closes the re-check items |
| 2 | weekly KPIs, state performance/mix decomposition, stage timing, seller queue, SQL check, interactive review | completed locally; see `docs/STAGE2_HANDOFF.md` |
| 3 | time-split features, baseline + logistic regression + gradient boosting | verified with stated assumptions; see `docs/STAGE3_HANDOFF.md`, `docs/model_card.md` |
| 3b | delay ↔ review association (optional) | not started; needs separate approval |
| 4 | three linked HTML pages, UAT, refresh checklist, manager handoff | complete; v0.4.1 makes the gate fail closed; see `docs/STAGE4_HANDOFF.md`, `outputs/stage4/UAT.md` |
| 5 | monthly rolling-origin backtest (2018-04/05/06), stage-3 models reused | published with limits: a ranking signal in each month, stability not established; not a new test; `outputs/stage5_backtest_report.md` |
| 6a | survival feasibility review: final-file vs as-of view, censoring candidates, conflicts | rev. 2 (v0.5.2); `docs/STAGE6A_SURVIVAL_FEASIBILITY.md` |
| 7 | promised-date policies (state rule, quantile regression, conformal shift) and monitoring (threshold rule; registered CUSUM run as a single-week LLR rule, deviation D1) | exploratory, pre-registered; complex model not kept; state rule 3.0 days shorter than Olist at −0.8 pts coverage (within the registered tolerance, no interval); alarm-rule comparison not established; `docs/STAGE7_DATE_POLICY.md` |
| 6b | survival model | not started; owner chooses O1 / O2 / O3 first |

## View the pages

Open `outputs/weekly_review.html` directly in a browser (no server, no network), or:
```bash
python -m http.server 4182 --bind 127.0.0.1 --directory outputs
# http://127.0.0.1:4182/weekly_review.html  ·  data_quality.html  ·  model_report.html
```

The review HTML embeds aggregate data and can be read offline. CSV/JSON source links
resolve beside it in `outputs/`. Figure 04A's selector affects that comparison only;
the trend, stage distributions and seller queue retain the full window.
The ZIP excludes raw CSVs, order-level marts, caches and historical copies. Put the
original nine files in `data/raw/` to rerun both stages. Aggregate results alone do
not establish causes or improved business performance.

## Stage 3 revision

v0.3.0 parameter selection included 3,807 development labels that were not yet known
when the test period began. v0.3.1 selects on the remaining 16,577 orders, retains the
same small candidate grid, and reruns the models. Logistic remains the development-selected
headline: test AP 0.12346; precision/recall at top 10% per purchase week 13.04% / 30.47%.
The re-evaluated test set is not fresh. Keep the estimated-date assumption, no-estimate
sensitivity and calibration limitation with any portfolio result.
