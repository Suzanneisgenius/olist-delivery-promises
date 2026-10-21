# Reproducing E1

Corrected 2026-10-21 (recipe B source layout; folder name; see `docs/REPRODUCE_E1_ERRATUM_2026-10-21.md`) and again
2026-10-21 after the fourth review (recipe B read FREEZE.json after it had been moved; one saved directory per recipe;
test count); see `docs/REPRODUCE_E1_ERRATUM_2026-10-21b.md`.

This snapshot contains code and E1 outputs. It does NOT contain the Olist raw CSVs or the order-level marts.
Two different things can be reproduced; keep them apart.

| Goal | Source code to use | Result |
|---|---|---|
| A. Check the saved results (no raw data) | current `src/` | recomputes every reported number from saved files |
| B. Reproduce the historical E1 run | `snapshots/src_at_e1_scoring/`, copied to the ordinary `src/` location in its own copy (fingerprint 6eac633d…af40 = `scoring_code_sha256` in the historical FREEZE.json) | a new run of the code that produced the reported results |
| C. Validate the hardened version | current `src/`, in a SEPARATE fresh copy (never the copy switched to historical source for B) | a NEW run with its own new freeze (input content hashed inside the freeze) |

Never disable or bypass the code-fingerprint check to make the historical FREEZE.json run with the current code.
The current code refuses it on purpose: it is not the code that was frozen.

## A. Check the saved results (no raw data needed)
```
pip install -r requirements-e1-tested.txt
export PYTHONPATH="$PWD/src"
python -m pytest -q                       # 362 tests in the r5 review package (345 in r4; 317 in the sealed v2 snapshot); E1 tests use synthetic data only
python3 scripts/e1_verify_score.py        # every E1 number from the saved per-order files: 43 / 43
python3 scripts/e1_verify_supplementary.py  # post-hoc V numbers and both simulation runs: 43 / 43
```

## Common preparation for B and C (needs the raw data)
Work in a FRESH copy of this snapshot, never in the copy that holds the evidence you want to compare against.
Run it once per recipe, each time in its own fresh copy and with its own saved directory (`RECIPE=B`, then later
`RECIPE=C` in a second copy), so the two runs never overwrite or nest inside each other.
```
set -euo pipefail                         # stop at the first failing command
RECIPE=B                                  # B or C
SNAP=/path/to/olist-e1-snapshot-v2        # the unpacked snapshot (or review package) folder; it is only read
WORK=/path/to/e1-rerun-$RECIPE            # must not exist yet
cp -r "$SNAP" "$WORK" && cd "$WORK"
SAVED="$WORK-saved"                       # outside the copy, one per recipe
# put the nine public Olist CSVs (Kaggle "Brazilian E-Commerce Public Dataset by Olist") into data/raw/;
# outputs/qa/source_manifest.csv lists their expected SHA-256
mkdir "$SAVED"                            # fails if it already exists: nothing is overwritten
mv outputs/e1/select outputs/e1/select_repro1 outputs/e1/final outputs/e1/freeze outputs/e1/models outputs/e1/score "$SAVED"/
```
Each E1 stage refuses to write into a directory that already holds results, which is why the saved ones are moved
aside. From here on the saved historical freeze is `$SAVED/freeze/FREEZE.json`; nothing is left at
`outputs/e1/freeze/`. Keep `WORK` and `SAVED` set in the same shell for the recipe that follows.

## B. Reproduce the historical run (scoring-time code)
The historical code finds the project root from its own location (`io.py`: `Path(__file__).resolve().parents[2]`),
so it must sit at `src/olist_analytics/`. Pointing PYTHONPATH at `snapshots/src_at_e1_scoring` makes it treat
`snapshots/` as the root and fail (`FileNotFoundError: .../snapshots/config/data_contract.yaml`). In the
disposable copy for B only, put the historical source in the ordinary place. Do not edit its root calculation.
```
set -euo pipefail
mv src src_hardened_preserved                 # keep the hardened source aside, untouched
cp -R snapshots/src_at_e1_scoring src
export PYTHONPATH="$PWD/src"
python -c "from olist_analytics import e1_freeze as Z; from pathlib import Path; import json, sys; \
assert Z.code_fingerprint(Path('src/olist_analytics'))[0] == json.load(open(sys.argv[1]))['scoring_code_sha256']; \
print('historical source in place; fingerprint matches the saved freeze')" "$SAVED/freeze/FREEZE.json"
python -m olist_analytics.run_all          # stages 1-7; rebuilds outputs/marts and outputs/stage7
python -m olist_analytics.run_e1 prep      # run the next line only if this one succeeded
python -m olist_analytics.run_e1 select
python -m olist_analytics.run_e1 fit-freeze
python -m olist_analytics.run_e1 score
```
Then compare with the saved run, for example:
```
diff "$SAVED/score/policy_table.csv" outputs/e1/score/policy_table.csv
diff "$SAVED/select/linear_ablation.csv" outputs/e1/select/linear_ablation.csv
python3 -c "import json, sys; a=json.load(open(sys.argv[1])); b=json.load(open('outputs/e1/score/results.json')); print({k: a[k] == b[k] for k in ('H1', 'H2', 'H3', 'M_vs_olist')})" "$SAVED/score/results.json"
```
Timestamps, registration files and FREEZE.json itself will differ (they record times); the numbers should not.
This code has no input-content hashing; the post-hoc addendum is not part of recipe B.

## C. Validate the hardened version (current code, new freeze)
In a separate fresh copy (common preparation again with `RECIPE=C`, so `WORK=/path/to/e1-rerun-C` and its own
`SAVED`), with the current `src/` left in place:
```
set -euo pipefail
export PYTHONPATH="$PWD/src"
python -m olist_analytics.run_all
python -m olist_analytics.run_e1 prep
python -m olist_analytics.run_e1 select
python -m olist_analytics.run_e1 fit-freeze   # the new FREEZE.json records input content hashes inline
python -m olist_analytics.run_e1 score
```
This produces its own registrations and its own freeze; it does not use or modify the historical FREEZE.json or the
addendum. Its numbers should match recipe B; its freeze hash will not.

## The post-hoc addendum
`outputs/e1/freeze/INPUT_IDENTITY_ADDENDUM.json` was written after the historical scoring. It records content hashes
of the inputs that were scored and is bound to the historical freeze by `applies_to_freeze_sha256`
(3b62af1a…328dd); the hardened entry accepts it only if that binding equals the actual FREEZE.json hash.
It is retrospective: it is not evidence that content checks existed before the original scoring.

Exploratory status: the evaluation orders had been examined in stage 7; E1 is a pre-registered exploratory
extension, scored once after its freeze, not a blind test.
