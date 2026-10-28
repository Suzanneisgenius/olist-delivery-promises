"""Targeted re-verification of the final E1 fixes (2026-10-21). Read-only with respect to the evidence.

Checks only what the last review asked for, plus the invariants that must not have moved:
  1. rounding helper refuses NaN / inf shifts, non-scalar shifts, empty / 2-d input, overflow, non-integer labels
  2. one-day-minimum boundary tests
  3. recipe B reads the saved freeze; acceptance runs B and C recorded
  4. main report, supplement and contribution statement carry the corrected wording (and not the old one)
  5. invariants: freeze, config, registered results, scoring code, model files unchanged

Each part is PASS, FAIL or SKIP. SKIP means the part could not run here (a tool or input is missing) and is never
counted as a pass. Part 4 reads the PDFs with pdftotext -raw (poppler) if it is installed, otherwise with pypdf if it
is importable (optional, not part of the recorded E1 environment: pip install pypdf==6.20.0), otherwise it is skipped.
A PDF that cannot be read is a FAIL.

Writes only <--out>/recheck.json (default AGENT_REVIEW/verify_output/, ignored by git). The record of the 2026-10-21
run, outputs/e1/final_recheck/recheck.json, is listed in the package manifest and is never written.
Exit status: 0 all PASS; 1 any FAIL; 3 no FAIL but at least one SKIP (verify_all.sh --strict counts that as a FAIL).
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEALED = ROOT / "outputs/e1/final_recheck"
ap = argparse.ArgumentParser(description="Targeted re-verification of the final E1 fixes (read-only).")
ap.add_argument("--out", type=Path, default=ROOT / "AGENT_REVIEW/verify_output", help="directory for recheck.json")
args = ap.parse_args()
OUT = args.out.resolve()
if OUT == SEALED.resolve():
    sys.exit(f"refusing to write into {SEALED.relative_to(ROOT)}/: it holds the sealed 2026-10-21 record")
OUT.mkdir(parents=True, exist_ok=True)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
res = {}


def mark(part, status):
    part["status"], part["ok"] = status, status == "PASS"
    return part


def worst(statuses):
    return "FAIL" if "FAIL" in statuses else "SKIP" if "SKIP" in statuses else "PASS"


def pytest_k(expr):
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-o", "pythonpath=",
                        "tests/test_posthoc_rounding.py", "-k", expr], cwd=ROOT, capture_output=True, text=True,
                       env={"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin:/usr/local/bin"})
    lines = r.stdout.strip().splitlines() or r.stderr.strip().splitlines() or ["no output"]
    last = re.sub(r" in [0-9.]+s", "", lines[-1])     # drop the timing so reruns are identical
    return mark({"selection": expr, "summary": last}, "PASS" if r.returncode == 0 and "failed" not in last else "FAIL")


# 1-2
res["1_helper_guards"] = pytest_k("refuses")
res["2_one_day_minimum_and_boundaries"] = pytest_k("minimum or boundary_cells or counterexample")

# 3
guide = (ROOT / "docs/REPRODUCE_E1.md").read_text()
recipe_b = guide.split("## B. Reproduce", 1)[1].split("\n## ", 1)[0]
acc = json.loads((ROOT / "outputs/e1/recipeB_acceptance/comparison.json").read_text())
summary = (ROOT / "outputs/e1/recipeB_acceptance/SUMMARY.md").read_text()
part3 = {
    "reads_saved_freeze": '"$SAVED/freeze/FREEZE.json"' in recipe_b,
    "no_read_of_moved_freeze": "outputs/e1/freeze/FREEZE.json" not in recipe_b,
    "per_recipe_saved_dir": 'SAVED="$WORK-saved"' in guide,
    "acceptance_B_e_per_order_equal": acc["e_per_order_equal"],
    "acceptance_B_shifts_equal": acc["freeze_shifts_equal"],
    "acceptance_B_model_hashes_equal": all(acc["freeze_model_file_hashes_equal"].values()),
    "acceptance_C_recorded": "## Recipe C" in summary and (ROOT / "outputs/e1/recipeB_acceptance/recipeC.log.gz").exists(),
}
res["3_recipe_b"] = mark(part3, "PASS" if all(part3.values()) else "FAIL")

# 4
def pdf_extractor():
    if shutil.which("pdftotext"):
        return "pdftotext -raw"
    try:
        import pypdf
    except ImportError:
        return None
    return f"pypdf {pypdf.__version__}"


def pdf_text(p, extractor):
    """Whitespace-normalised text of one PDF; raises if the file cannot be read or yields no text."""
    if extractor.startswith("pdftotext"):
        r = subprocess.run(["pdftotext", "-raw", str(p), "-"], capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(f"pdftotext exit {r.returncode}: {r.stderr.strip()[:200]}")
        text = r.stdout
    else:
        import pypdf
        text = "\n".join(page.extract_text() or "" for page in pypdf.PdfReader(p).pages)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        raise RuntimeError("no text extracted")
    return text


extractor = pdf_extractor()
unreadable = {}


def read(name):
    if not extractor:
        return ""
    try:
        return pdf_text(ROOT / "documents/current" / name, extractor)
    except Exception as e:  # missing, corrupt or empty PDF: its wording cannot be confirmed
        unreadable[name] = f"{type(e).__name__}: {e}"[:300]
        return ""


main, supp, note = map(read, ("E1_main_report.pdf", "E1_supplement.pdf", "E1_math_note_en.pdf"))
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
if extractor is None:
    res["4_documents"] = mark({"skipped": "neither pdftotext (poppler) nor pypdf is installed"}, "SKIP")
else:
    part4 = {k: (s in t) for k, (s, t) in want.items()}
    part4.update({k + " (absent)": (s not in t) for k, (s, t) in avoid.items()})
    held = all(part4.values()) and not unreadable
    res["4_documents"] = mark({"extractor": extractor, **part4, **({"unreadable": unreadable} if unreadable else {})},
                              "PASS" if held else "FAIL")

# 5
fr = json.loads((ROOT / "outputs/e1/freeze/FREEZE.json").read_text())
sys.path.insert(0, str(ROOT / "src"))
from olist_analytics import e1_freeze as Z  # noqa: E402
part5 = {
    "freeze_sha256": sha(ROOT / "outputs/e1/freeze/FREEZE.json") == "3b62af1ac385c2b8c9299e2e757a7e57e9ab2079526c9152878a1f5bfe8328dd",
    "config_sha256": sha(ROOT / "config/date_model_e1.yaml") == "ae6a4a4664c82124399d9da38354376955e6e783fd720eece608ac801eb20152",
    "scoring_snapshot_fingerprint": Z.code_fingerprint(ROOT / "snapshots/src_at_e1_scoring/olist_analytics")[0] == fr["scoring_code_sha256"]
    if (ROOT / "snapshots/src_at_e1_scoring").exists() else "SKIP: snapshot not in this tree",
    "model_files_match_freeze": all(sha(ROOT / "outputs/e1" / v["path"]) == v["sha256"] for v in fr["fitted_model_files_sha256"].values()),
    # equal to the sealed olist-e1-snapshot-v2 archive
    "registered_results_equal_sealed": sha(ROOT / "outputs/e1/score/results.json") == "6311324de36dac5dabb6cdfcd6da6895783ec85f7e5faecd859bd218e0f592c7",
    "registered_policy_table_equal_sealed": sha(ROOT / "outputs/e1/score/policy_table.csv") == "9c16f6ad60760c8f58aa9d8ad382ffe049bf8daedd1496572c060972defb7623",
}
res["5_invariants"] = mark(part5, worst(["SKIP" if isinstance(v, str) else "PASS" if v is True else "FAIL" for v in part5.values()]))

res["status"] = worst([v["status"] for v in res.values()])
res["all_ok"] = res["status"] == "PASS"
(OUT / "recheck.json").write_text(json.dumps(res, indent=2))
for k, v in res.items():
    print(k, v if not isinstance(v, dict) else (v["status"] if v["ok"] else json.dumps(v, indent=1)))
sys.exit({"PASS": 0, "FAIL": 1, "SKIP": 3}[res["status"]])
