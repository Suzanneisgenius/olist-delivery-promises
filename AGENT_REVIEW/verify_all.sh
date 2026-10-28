#!/usr/bin/env bash
# One-command check of everything that can be checked WITHOUT the raw Olist data.
# Run from the package root:  bash AGENT_REVIEW/verify_all.sh [--strict] [STEP ...]
#   --strict  a check that could not run here (SKIP) counts as a failure
#   STEP      run only the named steps, e.g. 01_manifest 10_final_recheck (the summary then says SELECTED)
# Read-only with respect to the evidence: everything it writes is under AGENT_REVIEW/verify_output/ (ignored by git),
# and the saved copies in outputs/e1/ are compared against, never rewritten.
# Each step is PASS, FAIL or SKIP. SKIP means a check could not run here, e.g. the PDF wording check with neither
# pdftotext nor pypdf installed; it is never reported as a pass. Only step 10 may skip: for the pytest steps exit 3
# means an internal error. Exit status: 0 pass, 1 fail, 3 skips.
set -uo pipefail
strict=0; only=""
for a in "$@"; do
  case "$a" in
    --strict) strict=1 ;;
    -*) echo "unknown option: $a"; exit 2 ;;
    *) only="$only $a" ;;
  esac
done
# -P: work in the physical directory, so PYTHONPATH matches the resolved package path that the entry-module
# provenance checks compare against, also when the package is reached through a symlink (e.g. /tmp on macOS).
cd -P "$(dirname "$0")/.."
OUT=AGENT_REVIEW/verify_output; mkdir -p "$OUT"
export PYTHONPATH="$PWD/src"
status=0; skipped=0; ran=""
# Preflight: fail early, with one clear message, if the tools the checks need are missing.
missing=""
python3 -c "import numpy, pandas, sklearn, scipy, yaml" 2>/dev/null || missing="$missing python:numpy/pandas/scikit-learn/scipy/pyyaml"
pytest_v=$(python3 -m pytest --version 2>&1) || missing="$missing python:pytest"
python3 -c "import duckdb" 2>/dev/null || missing="$missing python:duckdb"
command -v sha256sum >/dev/null || missing="$missing sha256sum"
if [ -n "$missing" ]; then
  echo "PREFLIGHT FAIL  missing:$missing"
  echo "Install the tested versions first:  pip install -r requirements-e1-tested.txt"
  exit 2
fi
echo "PREFLIGHT OK    $(python3 --version 2>&1); pytest $(echo "$pytest_v" | grep -o '[0-9][0-9.]*' | head -1)"
if ! command -v pdftotext >/dev/null && ! python3 -c "import pypdf" 2>/dev/null; then
  echo "PREFLIGHT NOTE  neither pdftotext (poppler) nor pypdf: step 10 cannot check the PDF wording and will be SKIP"
  echo "                (optional, not in the recorded E1 environment:  pip install pypdf==6.20.0)"
fi
[ -n "$only" ] && echo "SELECTED STEPS $only"
step() {
  local name="$1"; shift
  case " $only " in "  ") ;; *" $name "*) ;; *) return ;; esac
  ran="$ran $name"
  "$@" > "$OUT/$name.log" 2>&1; local rc=$?
  if [ $rc -eq 0 ]; then echo "PASS  $name"
  elif [ $rc -eq 3 ] && [ "$name" = 10_final_recheck ] && [ $strict -eq 0 ]; then
    echo "SKIP  $name (a check could not run here; see $OUT/$name.log)"; skipped=$((skipped + 1))
  else echo "FAIL  $name (see $OUT/$name.log)"; status=1; fi
}

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
step 07_recompute_E         python3 scripts/e1_verify_score.py "$OUT"
step 08_recompute_supp      python3 scripts/e1_verify_supplementary.py "$OUT"
step 09_claims              python3 AGENT_REVIEW/check_claims.py
step 10_final_recheck       python3 scripts/e1_final_recheck.py --out "$OUT"
step 11_harness             python3 -m pytest -q -p no:cacheprovider -o pythonpath= AGENT_REVIEW/harness_tests
for n in $only; do case " $ran " in *" $n "*) ;; *) echo "FAIL  $n (no such step)"; status=1 ;; esac; done
echo
sel=""; [ -n "$only" ] && sel="SELECTED "
if [ $status -ne 0 ]; then echo "SOME CHECKS FAILED"; exit 1; fi
if [ $skipped -gt 0 ]; then echo "${sel}CHECKS PASSED WITH SKIPS ($skipped): a skipped check did not run"; exit 3; fi
echo "${sel:-ALL }CHECKS PASSED"
