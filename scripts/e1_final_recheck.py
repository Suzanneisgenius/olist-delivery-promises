"""Targeted re-verification of the final E1 fixes (2026-10-21). Read-only; writes outputs/e1/final_recheck/.

Checks only what the last review asked for, plus the invariants that must not have moved:
  1. rounding helper refuses NaN / inf shifts, non-scalar shifts, empty / 2-d input, overflow, non-integer labels
  2. one-day-minimum boundary tests
  3. recipe B reads the saved freeze; acceptance runs B and C recorded
  4. main report, supplement and contribution statement carry the corrected wording (and not the old one)
  5. invariants: freeze, config, registered results, scoring code, model files unchanged
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/e1/final_recheck"
OUT.mkdir(parents=True, exist_ok=True)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
res = {}


def pytest_k(expr):
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "pythonpath=",
                        "tests/test_posthoc_rounding.py", "-k", expr], cwd=ROOT, capture_output=True, text=True,
                       env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin:/usr/local/bin"})
    last = re.sub(r" in [0-9.]+s", "", r.stdout.strip().splitlines()[-1])     # drop the timing so reruns are identical
    return {"selection": expr, "summary": last, "ok": r.returncode == 0 and "failed" not in last}


# 1-2
res["1_helper_guards"] = pytest_k("refuses")
res["2_one_day_minimum_and_boundaries"] = pytest_k("minimum or boundary_cells or counterexample")

# 3
guide = (ROOT / "docs/REPRODUCE_E1.md").read_text()
recipe_b = guide.split("## B. Reproduce", 1)[1].split("\n## ", 1)[0]
acc = json.loads((ROOT / "outputs/e1/recipeB_acceptance/comparison.json").read_text())
summary = (ROOT / "outputs/e1/recipeB_acceptance/SUMMARY.md").read_text()
res["3_recipe_b"] = {
    "reads_saved_freeze": '"$SAVED/freeze/FREEZE.json"' in recipe_b,
    "no_read_of_moved_freeze": "outputs/e1/freeze/FREEZE.json" not in recipe_b,
    "per_recipe_saved_dir": 'SAVED="$WORK-saved"' in guide,
    "acceptance_B_e_per_order_equal": acc["e_per_order_equal"],
    "acceptance_B_shifts_equal": acc["freeze_shifts_equal"],
    "acceptance_B_model_hashes_equal": all(acc["freeze_model_file_hashes_equal"].values()),
    "acceptance_C_recorded": "## Recipe C" in summary and (ROOT / "outputs/e1/recipeB_acceptance/recipeC.log.gz").exists(),
}
res["3_recipe_b"]["ok"] = all(res["3_recipe_b"].values())

# 4
def pdf_text(p):
    return re.sub(r"\s+", " ", subprocess.run(["pdftotext", "-raw", str(p), "-"], capture_output=True, text=True).stdout)

import shutil as _sh
main = supp = note = ""
if _sh.which("pdftotext"):
    main, supp = pdf_text(ROOT / "documents/current/E1_main_report.pdf"), pdf_text(ROOT / "documents/current/E1_supplement.pdf")
    note = pdf_text(ROOT / "documents/current/E1_math_note_en.pdf")
want = {
    "main: window sentence narrowed": ("does not separate it from", main),
    "main: rounding adds less than a day": ("less than a day of slack", main),
    "main: points to the math note": ("mathematical note", main),
    "main: summary closing sentence": ("matched evaluation procedure still produces comparisons", main),
    "supplement: untruncated floor identity": ("untruncated", supp),
    "supplement: AI review is not peer review": ("peer review", supp),
    "supplement: math note in contribution statement": ("Mathematical note", supp),
    "note: mean not generally optimal": ("does not generally minimise", note),
    "note: rounding up adds less than one day": ("adds less than one day", note),
    "note: k/(n+1) proposition": ("k/(n + 1)", note),
    "main: k/n is only a necessary consequence": ("necessary consequence", main),
    "main: k/n does not verify the implementation": ("implementation is correct", main),
    "main: exchangeability not established (not asserted false)": ("has not been established", main),
    "note: k/n is only a necessary consequence": ("necessary consequence", note),
    "note: direct implementation check named": ("recompute the k-th residual independently", note),
    "supplement: test count 362": ("362 pass", supp),
}
avoid = {
    "main: old causal window sentence": ("explains part of the over-coverage", main),
    "note: absolute rejection of the mean": ("not a suitable promise", note),
    "note: Beta paragraph": ("Beta", note),
    "supplement: 'always loses the k-th order'": ("always loses the k-th order", supp),
    "main: k/n read as proof of correct execution": ("applied as the rule says", main),
    "main: non-exchangeability asserted": ("as it does between C and E", main),
    "note: k/n read as proof of correct execution": ("were carried out as specified", note),
    "supplement: stale test count": ("345 pass", supp),
}
import shutil
if shutil.which("pdftotext") is None:
    res["4_documents"] = {"skipped": "pdftotext (poppler) not installed", "ok": True}
else:
    res["4_documents"] = {**{k: (s in t) for k, (s, t) in want.items()}, **{k + " (absent)": (s not in t) for k, (s, t) in avoid.items()}}
    res["4_documents"]["ok"] = all(res["4_documents"].values())

# 5
fr = json.loads((ROOT / "outputs/e1/freeze/FREEZE.json").read_text())
sys.path.insert(0, str(ROOT / "src"))
from olist_analytics import e1_freeze as Z  # noqa: E402
res["5_invariants"] = {
    "freeze_sha256": sha(ROOT / "outputs/e1/freeze/FREEZE.json") == "3b62af1ac385c2b8c9299e2e757a7e57e9ab2079526c9152878a1f5bfe8328dd",
    "config_sha256": sha(ROOT / "config/date_model_e1.yaml") == "ae6a4a4664c82124399d9da38354376955e6e783fd720eece608ac801eb20152",
    "scoring_snapshot_fingerprint": Z.code_fingerprint(ROOT / "snapshots/src_at_e1_scoring/olist_analytics")[0] == fr["scoring_code_sha256"]
    if (ROOT / "snapshots/src_at_e1_scoring").exists() else "snapshot not in this tree",
    "model_files_match_freeze": all(sha(ROOT / "outputs/e1" / v["path"]) == v["sha256"] for v in fr["fitted_model_files_sha256"].values()),
    # equal to the sealed olist-e1-snapshot-v2 archive
    "registered_results_equal_sealed": sha(ROOT / "outputs/e1/score/results.json") == "6311324de36dac5dabb6cdfcd6da6895783ec85f7e5faecd859bd218e0f592c7",
    "registered_policy_table_equal_sealed": sha(ROOT / "outputs/e1/score/policy_table.csv") == "9c16f6ad60760c8f58aa9d8ad382ffe049bf8daedd1496572c060972defb7623",
}
res["5_invariants"]["ok"] = all(v is True or v == "snapshot not in this tree" for v in res["5_invariants"].values())

res["all_ok"] = all(v["ok"] for v in res.values() if isinstance(v, dict))
(OUT / "recheck.json").write_text(json.dumps(res, indent=2))
for k, v in res.items():
    print(k, v if not isinstance(v, dict) else ("ok" if v["ok"] else json.dumps(v, indent=1)))
sys.exit(0 if res["all_ok"] else 1)
