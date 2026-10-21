#!/usr/bin/env bash
set -x
set -euo pipefail                         # stop at the first failing command
RECIPE=B                                  # B or C
SNAP=/tmp/claude-0/-home-claude/d5525519-8a74-5b87-94ee-57a0c654c2a7/scratchpad/recipeB_test/olist-e1-snapshot-v2        # the unpacked snapshot (or review package) folder; it is only read
WORK=/tmp/claude-0/-home-claude/d5525519-8a74-5b87-94ee-57a0c654c2a7/scratchpad/recipeB_test/e1-rerun-$RECIPE            # must not exist yet
cp -r "$SNAP" "$WORK" && cd "$WORK"
SAVED="$WORK-saved"                       # outside the copy, one per recipe
cp /home/claude/olist063-e1/data/raw/*.csv data/raw/ 2>/dev/null || { mkdir -p data/raw; cp /home/claude/olist063-e1/data/raw/*.csv data/raw/; }
# put the nine public Olist CSVs (Kaggle "Brazilian E-Commerce Public Dataset by Olist") into data/raw/;
# outputs/qa/source_manifest.csv lists their expected SHA-256
mkdir "$SAVED"                            # fails if it already exists: nothing is overwritten
mv outputs/e1/select outputs/e1/select_repro1 outputs/e1/final outputs/e1/freeze outputs/e1/models outputs/e1/score "$SAVED"/

# ---- recipe B (verbatim) ----
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

# ---- compare (verbatim) ----
diff "$SAVED/score/policy_table.csv" outputs/e1/score/policy_table.csv
diff "$SAVED/select/linear_ablation.csv" outputs/e1/select/linear_ablation.csv
python3 -c "import json, sys; a=json.load(open(sys.argv[1])); b=json.load(open('outputs/e1/score/results.json')); print({k: a[k] == b[k] for k in ('H1', 'H2', 'H3', 'M_vs_olist')})" "$SAVED/score/results.json"
