#!/usr/bin/env bash
set -x
set -euo pipefail                         # stop at the first failing command
RECIPE=C                                  # B or C
SNAP=/tmp/claude-0/-home-claude/d5525519-8a74-5b87-94ee-57a0c654c2a7/scratchpad/recipeB_test/olist-e1-snapshot-v2        # the unpacked snapshot (or review package) folder; it is only read
WORK=/tmp/claude-0/-home-claude/d5525519-8a74-5b87-94ee-57a0c654c2a7/scratchpad/recipeB_test/e1-rerun-$RECIPE            # must not exist yet
cp -r "$SNAP" "$WORK" && cd "$WORK"
SAVED="$WORK-saved"                       # outside the copy, one per recipe
cp /home/claude/olist063-e1/data/raw/*.csv data/raw/
# put the nine public Olist CSVs (Kaggle "Brazilian E-Commerce Public Dataset by Olist") into data/raw/;
# outputs/qa/source_manifest.csv lists their expected SHA-256
mkdir "$SAVED"                            # fails if it already exists: nothing is overwritten
mv outputs/e1/select outputs/e1/select_repro1 outputs/e1/final outputs/e1/freeze outputs/e1/models outputs/e1/score "$SAVED"/

# ---- recipe C (verbatim) ----
set -euo pipefail
export PYTHONPATH="$PWD/src"
python -m olist_analytics.run_all
python -m olist_analytics.run_e1 prep
python -m olist_analytics.run_e1 select
python -m olist_analytics.run_e1 fit-freeze   # the new FREEZE.json records input content hashes inline
python -m olist_analytics.run_e1 score

# ---- compare (added) ----
python3 -c "import json, sys; a=json.load(open(sys.argv[1])); b=json.load(open('outputs/e1/score/results.json')); print({k: a[k] == b[k] for k in ('H1', 'H2', 'H3', 'M_vs_olist')})" "$SAVED/score/results.json"
diff "$SAVED/score/policy_table.csv" outputs/e1/score/policy_table.csv && echo policy_table identical
