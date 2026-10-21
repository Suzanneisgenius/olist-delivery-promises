# Erratum to docs/REPRODUCE_E1.md in olist-e1-snapshot-v2.zip (2026-10-21)

Applies to: `olist-e1-snapshot-v2.zip` (SHA-256 2b1135768dbf2a9a6c266fcfbf7a5a98409b96b22918ef7e0c49f5bd120326b4).
That archive stays unchanged. No result, freeze record, model or scoring-time source is affected; only the
instructions for re-running are.

## 1. Recipe B: the historical source must be at `src/`
The archive's recipe B sets `export PYTHONPATH="$PWD/snapshots/src_at_e1_scoring"`. The historical `io.py` derives the
project root as `Path(__file__).resolve().parents[2]`, which is then `snapshots/`, so the first import fails:
`FileNotFoundError: .../snapshots/config/data_contract.yaml`.

Corrected steps, in a disposable copy used only for recipe B:
```
set -euo pipefail
mv src src_hardened_preserved
cp -R snapshots/src_at_e1_scoring src
export PYTHONPATH="$PWD/src"
python -c "from olist_analytics import e1_freeze as Z; from pathlib import Path; import json; \
assert Z.code_fingerprint(Path('src/olist_analytics'))[0] == json.load(open('outputs/e1/freeze/FREEZE.json'))['scoring_code_sha256']; \
print('historical source in place; fingerprint matches the freeze')"
python -m olist_analytics.run_all
python -m olist_analytics.run_e1 prep
python -m olist_analytics.run_e1 select
python -m olist_analytics.run_e1 fit-freeze
python -m olist_analytics.run_e1 score
```
Checked 2026-10-21 in a fresh extraction of the v2 archive (imports and paths only; no model was fitted): the documented
layout reproduces the FileNotFoundError; the corrected layout resolves the project root and config, the source
fingerprint is 6eac633d5e0838f59fe1ec665007ef6bab321ab52fc049cedfab8b4e51dcaf40 (= the freeze's scoring_code_sha256),
and the historical code has no input-identity helper, as expected. Do not edit the historical root calculation or
disable its fingerprint check.

## 2. Folder name
In "Common preparation", `cp -r olist-e1-snapshot ...` should read `cp -r olist-e1-snapshot-v2 ...`.

## 3. Recipe C uses a separate copy
Run recipe C in a second fresh copy that keeps the current (hardened) `src/`, never in the copy switched to the
historical source for recipe B.
