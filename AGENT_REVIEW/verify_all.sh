#!/usr/bin/env bash
# One-command check of everything that can be checked WITHOUT the raw Olist data.
# Run from the package root:  bash AGENT_REVIEW/verify_all.sh
# Read-only with respect to the evidence: it writes only under AGENT_REVIEW/verify_output/ (and pytest's tmp dirs).
# The two recomputation scripts rewrite outputs/e1/score_verification.csv, supplementary_verification.csv and
# outputs/e1/posthoc/e_olist_interval.json with identical content; work in a copy if you need byte-level comparisons.
set -uo pipefail
cd "$(dirname "$0")/.."
OUT=AGENT_REVIEW/verify_output; mkdir -p "$OUT"
export PYTHONPATH="$PWD/src"
status=0
# Preflight: fail early, with one clear message, if the tools the checks need are missing.
missing=""
python3 -c "import numpy, pandas, sklearn, scipy, yaml" 2>/dev/null || missing="$missing python:numpy/pandas/scikit-learn/scipy/pyyaml"
python3 -m pytest --version >/dev/null 2>&1 || missing="$missing python:pytest"
python3 -c "import duckdb" 2>/dev/null || missing="$missing python:duckdb"
command -v sha256sum >/dev/null || missing="$missing sha256sum"
if [ -n "$missing" ]; then
  echo "PREFLIGHT FAIL  missing:$missing"
  echo "Install the tested versions first:  pip install -r requirements-e1-tested.txt"
  exit 2
fi
echo "PREFLIGHT OK    $(python3 --version 2>&1); pytest $(python3 -m pytest --version 2>&1 | grep -o '[0-9][0-9.]*' | head -1)"
step() { local name="$1"; shift; if "$@" > "$OUT/$name.log" 2>&1; then echo "PASS  $name"; else echo "FAIL  $name (see $OUT/$name.log)"; status=1; fi; }

step 01_manifest            sha256sum -c AGENT_REVIEW/PACKAGE_MANIFEST.sha256 --quiet
step 02_config_hash         bash -c '[ "$(sha256sum config/date_model_e1.yaml | cut -c1-64)" = "$(head -1 outputs/e1/PREREGISTRATION_SHA256.txt | cut -c1-64)" ]'
step 03_freeze_hash         bash -c '[ "$(sha256sum outputs/e1/freeze/FREEZE.json | cut -c1-64)" = "$(cut -c1-64 outputs/e1/freeze/FREEZE.sha256)" ] && [ "$(cut -c1-64 outputs/e1/freeze/FREEZE.sha256)" = "3b62af1ac385c2b8c9299e2e757a7e57e9ab2079526c9152878a1f5bfe8328dd" ]'
step 04_scoring_source      python3 -c "
from olist_analytics import e1_freeze as Z; from pathlib import Path; import json, sys
fp = Z.code_fingerprint(Path('snapshots/src_at_e1_scoring/olist_analytics'))[0]
sys.exit(0 if fp == json.load(open('outputs/e1/freeze/FREEZE.json'))['scoring_code_sha256'] else 1)"
step 05_addendum_binding    python3 -c "
from olist_analytics import e1_pipeline as P
P.read_bound_addendum(P.OUT/'freeze'/P.INPUT_ADDENDUM, P.OUT/'freeze'/'FREEZE.json'); print('addendum bound to this FREEZE')"
step 06_pytest              python3 -m pytest -q -p no:cacheprovider -o pythonpath= --junitxml="$OUT/pytest_junit.xml"
step 07_recompute_E         python3 scripts/e1_verify_score.py
step 08_recompute_supp      python3 scripts/e1_verify_supplementary.py
step 09_claims              python3 AGENT_REVIEW/check_claims.py
step 10_final_recheck       python3 scripts/e1_final_recheck.py
echo; [ $status -eq 0 ] && echo "ALL CHECKS PASSED" || echo "SOME CHECKS FAILED"
exit $status
