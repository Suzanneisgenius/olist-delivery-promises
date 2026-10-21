#!/usr/bin/env bash
# Failure drills on a DISPOSABLE copy of the project — never on your working copy.
#
#   usage: failure_drills.sh <project-copy> <python> <evidence-dir>
#
# Each drill breaks one thing, runs the step a user would run next, and records the exit code, the full
# console output (<evidence-dir>/drill_logs/<id>.log), the block marker it left and one key assertion.
# Safety: backups go to a private `mktemp -d` folder; the nine raw CSVs are checked before any drill; a trap
# restores them on any exit and deletes the backup folder ONLY if every file was copied back and compares
# byte-identical — otherwise the backup is kept, its path printed, and the script exits non-zero. Every command
# that is NOT expected to fail stops the script if it fails. A drill that unexpectedly succeeds, or whose
# assertion text is missing, is recorded and makes the script exit non-zero at the end.
# Text edits use Python, so it runs on Linux and macOS.
set -euo pipefail

P=$(cd "$1" && pwd); PY=$2; EV=$(mkdir -p "$3" && cd "$3" && pwd)
RAW=(olist_customers_dataset.csv olist_geolocation_dataset.csv olist_order_items_dataset.csv
     olist_order_payments_dataset.csv olist_order_reviews_dataset.csv olist_orders_dataset.csv
     olist_products_dataset.csv olist_sellers_dataset.csv product_category_name_translation.csv)
[[ -f "$P/pyproject.toml" && -d "$P/src/olist_analytics" ]] || { echo "not a project copy: $P" >&2; exit 2; }
for f in "${RAW[@]}"; do [[ -f "$P/data/raw/$f" ]] || { echo "missing raw file: $f" >&2; exit 2; }; done

BAK=$(mktemp -d "${TMPDIR:-/tmp}/olist_drills.XXXXXX")
for f in "${RAW[@]}"; do cp "$P/data/raw/$f" "$BAK/$f"; done
restore() {                                                      # explicit status: safe inside `if`/`||`
  local f ok=0
  for f in "${RAW[@]}"; do cp "$BAK/$f" "$P/data/raw/$f" || ok=1; done
  for f in "${RAW[@]}"; do cmp -s "$BAK/$f" "$P/data/raw/$f" || ok=1; done
  return $ok
}
cleanup() {
  local rc=$?
  if restore; then
    rm -rf -- "$BAK"
  else
    echo "WARNING: restore failed or files differ; originals KEPT in $BAK" >&2
    rc=1
  fi
  trap - EXIT
  exit $rc
}
trap cleanup EXIT
trap 'exit 130' INT TERM                                         # make sure the EXIT trap runs on interrupt

cd "$P"; export PYTHONPATH=src
LOGS="$EV/drill_logs"; mkdir -p "$LOGS"; OUT="$EV/failure_drills.jsonl"; : > "$OUT"
ok() { "$@" > /dev/null 2>&1; }                                   # must succeed (set -e stops otherwise)
DRILL_FAIL=0
must_restore() { restore || { echo "restore failed" >&2; exit 1; }; }

expect_fail() {   # id, description, marker, assertion-text, command...
  local id=$1 desc=$2 marker=$3 needle=$4; shift 4
  local start rc; start=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  set +e; "$@" > "$LOGS/$id.log" 2>&1; rc=$?; set -e
  if ! "$PY" - "$OUT" "$id" "$desc" "$rc" "$marker" "$needle" "$LOGS/$id.log" "$start" <<'PYEOF'
import json, pathlib, sys
out, did, desc, rc, marker, needle, log, start = sys.argv[1:9]
m, logtext = pathlib.Path(marker), pathlib.Path(log).read_text(errors="replace")
if not m.exists():
    content = None
elif m.suffix == ".json":
    try:
        data = json.loads(m.read_text())
        content = [r.get("check") for r in data] if isinstance(data, list) else data
    except ValueError as e:
        content = f"unparseable JSON: {e}"
else:                                                             # Markdown / CSV: keep the lines that matter
    lines = m.read_text(errors="replace").splitlines()
    content = [l for l in lines if "**NO**" in l or "BLOCKED" in l or "Automated:" in l][:15]
haystack = logtext + "\n" + (json.dumps(content) if content is not None else "")
rec = {"drill": did, "description": desc, "started_utc": start, "exit_code": int(rc), "expected_nonzero": int(rc) != 0,
       "marker": marker, "marker_exists": m.exists(), "marker_content": content,
       "assertion": needle, "assertion_found": needle in haystack,
       "current_pages_after": sorted(p.name for p in pathlib.Path("outputs").glob("*.html")),
       "log": str(pathlib.Path(log).name), "log_tail": logtext.strip().splitlines()[-3:]}
open(out, "a").write(json.dumps(rec) + "\n")
print(f"{did}: exit {rc}, assertion {'found' if rec['assertion_found'] else 'NOT FOUND'}")
sys.exit(0 if rec["expected_nonzero"] and rec["assertion_found"] else 3)
PYEOF
  then DRILL_FAIL=1; echo "$id: DRILL FAILED (unexpected success or assertion missing)" >&2; fi
}
edit_text() { "$PY" - "$1" "$2" "$3" <<'PYEOF'
import pathlib, sys
p, old, new = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
s = p.read_text()
assert old in s, f"text not found in {p}"
p.write_text(s.replace(old, new, 1))
PYEOF
}

echo "baseline"; ok "$PY" -m olist_analytics.run_all

mv data/raw/olist_sellers_dataset.csv "$BAK/sellers.moved"
expect_fail D1 "missing raw CSV (sellers) -> run_all" outputs/qa/RELEASE_BLOCKED.json "olist_sellers_dataset.csv" \
  "$PY" -m olist_analytics.run_all
mv "$BAK/sellers.moved" data/raw/olist_sellers_dataset.csv

head -n 98000 "$BAK/olist_orders_dataset.csv" > data/raw/olist_orders_dataset.csv
expect_fail D2 "truncated orders CSV (97,999 rows) -> run_all" outputs/qa/RELEASE_BLOCKED.json "SQL item lines" \
  "$PY" -m olist_analytics.run_all
must_restore; ok "$PY" -m olist_analytics.run_all

printf '\n' >> data/raw/olist_order_reviews_dataset.csv
expect_fail D3a "raw file changed after stage 1 -> stage 3" outputs/stage3/qa/RELEASE_BLOCKED.json \
  "source changed since stage 1" "$PY" -m olist_analytics.run_stage3
expect_fail D3b "raw file changed after stage 1 -> independent verifier" outputs/stage3/qa/VERIFY_FAILED.json \
  "raw file changed" "$PY" -I scripts/verify_stage3.py
must_restore; ok "$PY" -m olist_analytics.run_all

rm -f outputs/stage3/independent_verification.json
expect_fail D4 "stage 4 without a fresh verification" outputs/stage4/qa/RELEASE_BLOCKED.json \
  "independent verification exists for this stage-3 run" "$PY" -m olist_analytics.run_stage4
ok "$PY" -I scripts/verify_stage3.py; ok "$PY" -m olist_analytics.run_stage4; ok "$PY" scripts/ui_check_stage4.py

cp outputs/model_report.html "$BAK/model_report.html"
edit_text outputs/model_report.html "Late-Delivery Risk Model" "Late-Delivery Risk Model (edited)"
expect_fail D5 "published page edited by hand -> UAT" outputs/stage4/UAT.md \
  "pages on disk == pages of the stage-4 release" "$PY" scripts/build_uat.py
cp "$BAK/model_report.html" outputs/model_report.html

ok "$PY" -m olist_analytics.run_stage4
expect_fail D6 "stage 4 rerun, browser checks not rerun -> UAT" outputs/stage4/ui_checks.csv \
  "missing evidence" "$PY" scripts/build_uat.py

echo "restoring the copy to a full, passing state"
must_restore; ok "$PY" -m olist_analytics.run_all; ok "$PY" -m olist_analytics.survival_audit
ok "$PY" scripts/ui_check_stage4.py; ok "$PY" scripts/build_uat.py
echo "done: $OUT"
[[ $DRILL_FAIL -eq 0 ]] || { echo "one or more drills did not behave as expected" >&2; exit 1; }
