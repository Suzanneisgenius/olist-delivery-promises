# Refresh checklist

Use when the raw files change (new download) or any config changes. One sitting, same steps every time.

## Before
- [ ] Put the nine Olist CSVs in `data/raw/` (never edit them by hand).
- [ ] If the files are a new download: note the date and Kaggle version in `config/assumptions.yaml`.
- [ ] If a decision changed (window, KPI, model protocol): update `config/approvals.yaml` / `config/model.yaml` first.

## Run
- [ ] `PYTHONPATH=src python -m olist_analytics.run_all` — stage 1 → 2 → 3 → independent verification → 4 → 5; stops at the first failure.
- [ ] If a step blocks: read its marker (`outputs/qa/`, `outputs/stage2/qa/`, `outputs/stage3/qa/RELEASE_BLOCKED.json` or `VERIFY_FAILED.json`, `outputs/stage4/qa/`, `outputs/stage5/qa/`), fix the cause, rerun. Never edit an output to make a check pass.
- [ ] `python scripts/ui_check_stage4.py` — browser checks on the current pages; evidence is bound to their SHA-256.
- [ ] `PYTHONPATH=src python scripts/build_uat.py` — runs the full test suite; exits 1 if any test fails or any evidence is stale.

## Check what changed
- [ ] Source hashes in `outputs/qa/source_manifest.csv`: expected files only?
- [ ] Stage-1 report §11 says **READY**. If it says NEEDS_RE_APPROVAL, the computed window moved: decide, record it in `config/approvals.yaml`, rerun.
- [ ] Headline numbers vs the last release: window on-time rate, 74-week window, test AP. Explain any move before sharing.
- [ ] The test period has now been seen more than once; do not present it as a fresh confirmatory test.

## Before sharing
- [ ] Owner fills `reviewer_ok` / `reviewer_note` in `outputs/qa/manual_check_sample.csv` (UAT-13).
- [ ] Owner adds rows to `uat/owner_signoff.csv` (UAT-13, UAT-14) with the release hash printed at the top of `outputs/stage4/UAT.md`. A sign-off for another release is shown as stale.
- [ ] Limits travel with the numbers: censoring near the end, estimated-date assumption, miscalibrated probabilities, single-seller A/L population.
