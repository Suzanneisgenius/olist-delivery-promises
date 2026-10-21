#!/usr/bin/env bash
# Rebuild everything from the raw CSVs, write FRESH logs and run the release gate.
#   usage: scripts/make_release.sh <version> [python]
# Old release/ contents are removed first, so a package never carries logs from an earlier run.
# Owner UAT cases (UAT-13/14) are never signed here.
set -euo pipefail
V=$1; PY=${2:-python}
cd "$(dirname "$0")/.."
export PYTHONPATH=src
rm -rf release && mkdir -p release/logs
"$PY" -m olist_analytics.run_all 2>&1 | tee release/logs/run_all.log
"$PY" -m olist_analytics.survival_audit > release/logs/survival_audit.log 2>&1
"$PY" scripts/ui_check_stage4.py > release/logs/ui_check.log 2>&1
"$PY" -m pytest -q -rA --junitxml=release/logs/pytest_junit.xml > release/logs/pytest.log 2>&1
"$PY" scripts/build_uat.py > release/logs/build_uat.log 2>&1
"$PY" -I scripts/release_evidence.py "$V"
