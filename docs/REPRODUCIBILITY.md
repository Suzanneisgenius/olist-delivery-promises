# Reproducibility check (v0.5.5)

**Question:** can someone rebuild the results from the nine raw Olist CSVs using only the README?
**Answer:** yes, in two fresh Linux environments. `run_all` rebuilds stages 1–5; browser checks, UAT and the stage-6a
audit are separate commands. Model inputs, predictions and reported metrics matched byte for byte between the two;
a few descriptive and cross-check files differ in the last floating-point digits (§3). Three README gaps were fixed (§4).
Machine records of these runs are in `docs/repro_evidence/` (§7). The Linux runs started from the v0.5.2 package; the
computation code, configs and tests are unchanged through v0.5.5, so they count as inherited evidence for v0.5.5, not as a
new clean install of it.

Run on 2026-10-13 in a cloud Linux workspace (2 CPU, 7 GB RAM). Starting point for each run: the v0.5.2 ZIP unpacked
into a new folder, its shipped `outputs/` moved aside, the nine raw CSVs copied into `data/raw/`, a new virtual environment.

## 1. Environments

| | A — pinned (owner's versions) | B — README install |
|---|---|---|
| Python | 3.12.3 | 3.13.16 |
| Install | `pip install -r requirements-tested.txt` (71 s) | `pip install -e .` (32 s) |
| pandas / NumPy | 2.3.3 / 2.5.1 | 3.0.6 / 2.5.4 |
| scikit-learn / SciPy | 1.9.0 / 1.18.1 | 1.9.1 / 1.18.1 |
| DuckDB / PyYAML / pytest | 1.5.5 / 6.0.3 / 8.4.2 | 1.5.6 / 6.0.3 / 9.1.1 |
| Playwright (browser checks only) | 1.56.0 | 1.56.0 |

## 2. Steps and timings (README order)

| Step | A | B | Result |
|---|---:|---:|---|
| `python -m olist_analytics.run_all` (1 → 2 → 3 → verify → 4 → 5) | 1 min 45 s | 1 min 52 s | all steps ok; stage 3 is the slowest (48–50 s) |
| `python scripts/ui_check_stage4.py` | 8 s | 8 s | 33 / 33 |
| `python scripts/build_uat.py` | 6 s | 5 s | 12 / 12 automated; pytest 110 / 110 inside |
| `python -m olist_analytics.survival_audit` | 5 s | ~5 s | ok |
| `python -m pytest -q` | 4 s | 3 s | 110 passed (A: deprecation warnings from pandas 2.3.3 timedelta units; B: none) |

Total from an empty folder to a full release with automated UAT (not the owner's UAT-13/14): about 3–4 minutes plus installation.

## 3. Are the results the same?

- **A vs B, both in the same complete state** (after B's drills: `run_all`, stage-6a audit, browser checks and UAT
  rerun on both, all passing — `envA_final_*`, `envB_final_*`): 60 files identical, 15 different, none on one side only
  (`repro_evidence/compare_envA_vs_envB.json`, which stores both hashes for every file). Identical: the mart, outcome
  buckets, weekly KPIs, decomposition, test predictions and metrics, fold predictions and metrics, the stage-6a category
  and unresolved tables, the weekly and data-quality pages. Different: run metadata (timestamps, environment strings,
  lineage files, the JUnit report; the model page, UAT and browser-evidence files, which print hashes of those
  timestamped files) and **minor numeric differences** — the last digits of three columns in
  `sql_stage_timing_crosscheck.csv` (the check still passes) and of two 99.9th percentiles in the stage-6a descriptive
  facts (e.g. 83.14106533565 vs 83.14106533564 days).
- **A vs the shipped v0.5.2 outputs:** the same pattern — run metadata and minor numeric differences
  (`repro_evidence/compare_envA_vs_shipped_v0.5.2.json`; the shipped set has a stage-2 preview image A does not make).
- **A third run: an independent Codex-assisted local review on the owner's Mac** (macOS, Python 3.12.14, pandas 2.3.3,
  reported in the v0.5.3 review; its evidence is not in this package). Headline results and selected counts were
  unchanged; logistic fold scores matched within numerical tolerance (largest difference ~3e-13); one of 18,865 GBM
  fold scores differed visibly (0.02463 vs 0.02626), and several GBM metrics differed slightly (AP by ~7e-8, AUC by
  ~3e-6), with identical selections and hits. A repeat on that machine matched itself byte for byte. The cause was not
  isolated (platform and several library versions differ). **Byte-identical output is not claimed across platforms.**
- This closes the earlier gap "not retested on the owner's Python 3.12 / pandas 2.3.3" (Python 3.12.3 here; 3.12.14 in the owner's run).

## 4. Problems found in the README (fixed in v0.5.3)

| Problem | Seen | Fix |
|---|---|---|
| Browser checks need Playwright, which is not a project dependency | `ModuleNotFoundError: playwright` | README states the optional install |
| The newest Playwright (1.63.0) asked for a browser download that did not match the installed Chromium | "Please run `playwright install`" | README: install Playwright and its own browser together (`pip install playwright && playwright install chromium`), or pin the version that matches an existing browser (1.56.0 here). The first route was not run here: this workspace does not allow browser downloads |
| `PYTHONPATH=src` is required unless the package is installed | `ModuleNotFoundError: olist_analytics` (env A) | README says when it is needed; with `pip install -e .` it is not |

## 5. Failure handling (drills on a disposable copy)

`repro_evidence/failure_drills.sh` runs the drills; each one's exit code, block marker, a key assertion and the full
console output are in `repro_evidence/envB_drills/` (`failure_drills.jsonl`, `drill_logs/D*.log`). Rerun on env B for
v0.5.5: all seven records exit 1 and all seven assertions are found. Drills 1–4 leave no page or report from the failed
run. In drills 5–6 the pages stay (they are the current stage-4 release); what fails is UAT, which refuses evidence that
does not match them. After the drills the script restores the copy and reruns everything to a passing state.

| Drill | What happened | Recorded evidence |
|---|---|---|
| D1 raw CSV missing (`olist_sellers_dataset.csv`) | stage 1 stops (`FileNotFoundError`), exit 1; nothing downstream runs | marker `run completed` failed; log names the file |
| D2 truncated download (orders cut to 97,999 rows) | stage 1 blocks: item lines and price sum differ from the raw-SQL count | marker lists both checks |
| D3a raw file changed after stage 1 (one byte appended to reviews) → stage 3 | blocked: "source changed since stage 1" | marker |
| D3b same → independent verifier | fails, writes `VERIFY_FAILED.json`, leaves no verification file | marker lists the changed file |
| D4 stage 4 without a fresh verification | blocked: "independent verification exists for this stage-3 run"; no page written | marker |
| D5 a published page edited by hand → UAT | exit 1; "0 of 12 pass — BLOCKED"; "pages on disk == pages of the stage-4 release: NO" | UAT lines kept as text |
| D6 stage 4 rerun, browser checks not rerun → UAT | exit 1: "UAT not built: missing evidence … ui_checks.csv" (old evidence retired with the old pages) | drill log |

Script safety: private `mktemp -d` backup folder (only that folder is removed), the nine raw files are checked first,
a trap restores them on any exit or interrupt, commands that should succeed stop the script if they fail, and text
edits use Python, so it runs on Linux and macOS (tested on Linux only). Use it only on a copy of the project.

What to do after a failure: read the named marker file, fix the cause (restore the file, rerun the earlier stage,
rerun the browser checks), and run again. Never edit an output to make a check pass (`docs/refresh_checklist.md`).

## 6. Not covered

- Windows was not tested. macOS was covered once by an independent Codex-assisted review on the owner's Mac (§3), outside this package's evidence.
- A new Kaggle download was not tested (same nine files, same hashes). A changed download is expected to give new numbers
  and, if the computed window moves, a NEEDS_RE_APPROVAL state; the refresh checklist covers that review.
- The owner's manual review (UAT-13) and sign-off (UAT-14) are not part of reproducibility.

## 7. Evidence files (`docs/repro_evidence/`)

| File | What it records |
|---|---|
| `platform.txt`, `envA_python3.12_freeze.txt`, `envB_python3.13_freeze.txt` | Python, OS/CPU, every installed package version |
| `envA_run_all.log`, `envA_run_all.time`, `envB_run_all.log`, `envB_run_all_rerun.log` | first runs of `run_all` (step output and timings) |
| `envA_ui.log`, `envA_uat.log`, `envA_audit.log`, `envA_pytest.log`, `envB_ui.log`, `envB_uat.log` | first runs of browser checks, UAT, stage-6a audit, tests |
| `envA_final_refresh.log`, `env{A,B}_final_UAT.md`, `env{A,B}_final_UI_CHECKS.md` | the final complete state of each environment that §3 compares |
| `compare_outputs.py`, `compare_envA_vs_envB.json`, `compare_envA_vs_shipped_v0.5.2.json` | comparison script; full manifests with both SHA-256 values for every file |
| `failure_drills.sh`, `envB_drills/failure_drills.jsonl`, `envB_drills/drill_logs/`, `envB_drills/console.log` | drills script, per-drill records and full logs |

The complete output folders of A and B are not included (they hold the order-level mart); the manifests let the
comparison be re-checked file by file against any rerun. No raw CSV is included.
