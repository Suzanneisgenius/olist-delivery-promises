"""Build outputs/stage4/UAT.md and outputs/stage4/uat_results.csv from the evidence of the current release.

    PYTHONPATH=src python scripts/build_uat.py      (after run_all and scripts/ui_check_stage4.py)

Fail closed
  - The whole pytest suite must pass: exit code 0, at least one test collected, no failure or error.
    Skipped tests are listed and never count as a pass for a case that relies on them.
  - The evidence must belong to the current release: stage 4 not blocked; the three pages match the
    stage-4 lineage; the browser evidence was produced on exactly these pages; the independent
    verification is bound to the current stage-3 files.
  If any of this fails, every automated case is BLOCKED and the script exits 1.

Owner sign-off lives in uat/owner_signoff.csv, which this script never writes (it only creates the
header if the file is missing). A sign-off counts only for the release it names (release_sha256 =
SHA-256 of outputs/stage4/lineage.json); a sign-off for another release is shown as stale.
Automated evidence is not business sign-off.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
S4 = OUT / "stage4"
SIGNOFF = ROOT / "uat" / "owner_signoff.csv"
SIGNOFF_COLS = ["id", "release_sha256", "reviewer", "date", "decision", "note"]
PAGE_KEYS = {"weekly": "weekly_review.html", "dq": "data_quality.html", "model": "model_report.html"}


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def md(v) -> str:
    """Escape a value for one Markdown table cell."""
    return str(v).replace("|", "\\|").replace("\r", " ").replace("\n", " ")


# ------------------------------------------------------------------ pytest
def parse_junit(xml_path: Path, returncode: int) -> dict:
    root = ET.parse(xml_path).getroot()
    outcomes = {}
    for tc in root.iter("testcase"):
        outcome = "passed"
        for child in tc:
            outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}.get(child.tag, outcome)
        outcomes[tc.get("name")] = outcome
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    suite_errors = sum(int(s.get("errors", 0)) for s in suites) - sum(v == "error" for v in outcomes.values())
    pick = lambda kind: sorted(k for k, v in outcomes.items() if v == kind)
    return {"returncode": returncode, "collected": len(outcomes), "outcomes": outcomes,
            "passed": pick("passed"), "failed": pick("failed"), "errors": pick("error"),
            "skipped": pick("skipped"), "suite_errors": max(suite_errors, 0)}


def pytest_ok(st: dict) -> bool:
    return (st["returncode"] == 0 and st["collected"] > 0 and not st["failed"] and not st["errors"]
            and st["suite_errors"] == 0)


def run_pytest() -> dict:
    xml = S4 / "pytest_junit.xml"
    xml.parent.mkdir(parents=True, exist_ok=True)
    if xml.exists():
        xml.unlink()
    r = subprocess.run([sys.executable, "-m", "pytest", "-q", f"--junitxml={xml}"], cwd=ROOT,
                       capture_output=True, text=True)
    if not xml.exists():
        return {"returncode": r.returncode, "collected": 0, "outcomes": {}, "passed": [], "failed": [],
                "errors": ["pytest produced no report"], "skipped": [], "suite_errors": 1}
    return parse_junit(xml, r.returncode)


# ------------------------------------------------------------------ evidence freshness
def evidence_status(out: Path = OUT) -> list[dict]:
    rows = []
    add = lambda c, ok, detail="": rows.append({"check": c, "pass": bool(ok), "detail": detail})
    s4 = out / "stage4"
    lineage_p = s4 / "lineage.json"
    add("stage 4 is not blocked", not (s4 / "qa" / "RELEASE_BLOCKED.json").exists())
    add("current stage-4 release exists", lineage_p.exists())
    if not lineage_p.exists():
        return rows
    lineage = json.loads(lineage_p.read_text())
    add("stage-4 release checks passed", lineage.get("checks_pass") is True)
    current = {name: sha(out / name) if (out / name).exists() else None for name in PAGE_KEYS.values()}
    add("pages on disk == pages of the stage-4 release", all(current[n] == lineage["pages"].get(k) for k, n in PAGE_KEYS.items()))
    ui_p = s4 / "ui_evidence.json"
    add("browser evidence exists", ui_p.exists())
    if ui_p.exists():
        ui = json.loads(ui_p.read_text())
        add("browser evidence: all checks passed", ui.get("checks_pass") is True)
        add("browser evidence was produced on these exact pages", ui.get("pages_sha256") == current)
        add("browser evidence belongs to the current stage-4 release", ui.get("stage4_lineage_sha256") == sha(lineage_p))
        add("browser check table unchanged since recorded",
            (s4 / "ui_checks.csv").exists() and ui.get("ui_checks_sha256") == sha(s4 / "ui_checks.csv"))
    from olist_analytics import run_stage4
    for r in run_stage4.verification_status():
        add(r["check"], r["actual"], r.get("detail", ""))
    return rows


# ------------------------------------------------------------------ owner sign-off (read only)
def read_signoff(path: Path, release: str) -> dict[str, str]:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(",".join(SIGNOFF_COLS) + "\n", encoding="utf-8")
    s = pd.read_csv(path, dtype=str).fillna("")
    shown = {}
    for r in s.itertuples():
        if r.release_sha256 == release:
            shown[r.id] = f"{r.decision} — {r.reviewer}, {r.date}" + (f" ({r.note})" if r.note else "")
        elif r.id not in shown:
            shown[r.id] = f"stale: signed for release {r.release_sha256[:12]}…, not this one"
    return shown


def rows_pass(df: pd.DataFrame, contains: str) -> tuple[bool, str]:
    m = df[df.check.str.contains(contains, regex=False)]
    if m.empty:
        return False, f"no check matching '{contains}'"
    ok = m["pass"].astype(str).isin(["True", "true"]).all()
    return bool(ok), "; ".join(f"{r.check}: {r.actual}" for r in m.itertuples())[:300]


def main() -> int:
    st = run_pytest()
    ev = evidence_status()
    pre_ok = pytest_ok(st) and all(r["pass"] for r in ev)
    t = st["outcomes"]
    passed = lambda name: t.get(name) == "passed"
    release = sha(S4 / "lineage.json") if (S4 / "lineage.json").exists() else ""

    cases = []
    def case(cid, criterion, evidence, ok, actual, owner_only=False):
        if owner_only:
            res = "n/a — owner review"
        elif not pre_ok:
            res = "BLOCKED"
        else:
            res = "PASS" if ok else "FAIL"
        cases.append({"id": cid, "acceptance criterion": criterion, "evidence": evidence,
                      "automated result": res, "actual": actual})

    try:
        s1 = pd.read_csv(OUT / "qa" / "reconciliation_checks.csv")
        s2 = pd.read_csv(OUT / "stage2" / "stage2_checks.csv")
        s3 = pd.read_csv(OUT / "stage3" / "stage3_checks.csv")
        s4 = pd.read_csv(S4 / "stage4_checks.csv")
        ui = pd.read_csv(S4 / "ui_checks.csv").rename(columns={"case": "check", "observed": "actual"})
        ver = json.loads((OUT / "stage3" / "independent_verification.json").read_text())
    except FileNotFoundError as e:
        print(f"UAT not built: missing evidence {e.filename}", file=sys.stderr)
        return 1
    sample = pd.read_csv(OUT / "qa" / "manual_check_sample.csv")
    gate_tests = [k for k in t if "block" in k or "refuse" in k or "failure" in k or "stale" in k]

    case("UAT-01", "Raw files are the fingerprinted ones", "stage4_checks.csv", *rows_pass(s4, "raw files unchanged"))
    a, b = rows_pass(s1, "orders_mart"), rows_pass(s1, "conserved")
    case("UAT-02", "One row per order; item lines, price, freight and payments conserved", "reconciliation_checks.csv",
         a[0] and b[0] and rows_pass(s1, "item lines carried")[0], "rows, uniqueness, item lines, price, freight, payments")
    case("UAT-03", "Outcome buckets are exclusive and match an independent SQL count", "reconciliation_checks.csv",
         *rows_pass(s1, "SQL outcome buckets"))
    case("UAT-04", "Weekly comparison uses exactly the approved 74-week window", "stage2_checks.csv",
         *rows_pass(s2, "window weeks used"))
    case("UAT-05", "Weekly page shows the KPI A/(A+L) with U, coverage and X; value equals stage-1 selection",
         "ui_checks.csv", *rows_pass(ui, "whole-window on-time"))
    case("UAT-06", "State decomposition adds up to the overall change for every weekly pair", "stage2_checks.csv",
         *rows_pass(s2, "decomposition identity"))
    case("UAT-07", "Stage-time anomalies do not remove orders from OTD", "pytest",
         passed("test_stage_anomaly_keeps_order_in_otd"), "test_stage_anomaly_keeps_order_in_otd")
    ok8 = all(rows_pass(s3, c)[0] for c in ("tuning fit uses only", "final fit uses only", "model selection uses only",
                                             "every seller snapshot"))
    case("UAT-08", "Model fit, model selection and seller history use only labels known at each cut-off",
         "stage3_checks.csv", ok8, "4 label-availability checks")
    case("UAT-09", "All test metrics of all three models re-derived without project code match the report",
         "independent_verification.json", ver.get("all_match") is True and rows_pass(s4, "== independent verification")[0],
         f"logistic AP {ver['score_checks']['logistic']['average_precision']:.5f}; "
         f"{len(ver['compared']['quantities_per_model'])} quantities x {len(ver['compared']['models'])} models + identities")
    ok10 = all(rows_pass(s4, c)[0] for c in ("embeds review_data", "buckets ==", "window ==", "AP / AUC",
                                             "independent verification", "precision = hits/selected")) \
        and all(rows_pass(ui, c)[0] for c in ("model page:", "data-quality page: orders"))
    case("UAT-10", "Numbers on the pages equal the exported files", "stage4_checks.csv + ui_checks.csv", ok10,
         "embedded data and displayed values compared")
    ok11 = all(rows_pass(ui, c)[0] for c in ("no console", "horizontal overflow"))
    case("UAT-11", "Pages load without errors in light/dark and at phone width (390 px)", "ui_checks.csv", ok11,
         f"{len(ui[ui.check.str.contains('console|overflow')])} page/width checks")
    case("UAT-12", "Any failed check blocks publication and removes the old report", "pytest",
         bool(gate_tests) and all(passed(k) for k in gate_tests), f"{len(gate_tests)} gate tests, all must pass (skipped ≠ pass)")
    case("UAT-13", "A person checks the 20-order sample against the raw files", "qa/manual_check_sample.csv", False,
         f"{int(sample.reviewer_ok.notna().sum())} of {len(sample)} reviewed", owner_only=True)
    case("UAT-14", "Owner accepts conclusions and stated limits (window censoring, estimate assumption, calibration)",
         "pages + reports", False, "pending", owner_only=True)

    signed = read_signoff(SIGNOFF, release)
    df = pd.DataFrame(cases)
    df["owner sign-off"] = df.id.map(signed).fillna("")
    df.to_csv(S4 / "uat_results.csv", index=False)
    auto = df[df["automated result"] != "n/a — owner review"]
    n_pass = int((auto["automated result"] == "PASS").sum())

    lines = ["# UAT — Olist Delivery Performance & Late-Delivery Risk", "",
             f"Release (SHA-256 of `outputs/stage4/lineage.json`): `{release}`", "",
             f"Generated by `scripts/build_uat.py`. Automated: **{n_pass} of {len(auto)} pass**"
             + ("" if pre_ok else " — **BLOCKED: preconditions below failed, results are not valid**") + ".",
             "Automated evidence is not business sign-off. Owner sign-off is read from `uat/owner_signoff.csv` "
             "and counts only for the release it names.", "",
             "## Preconditions", "", "| Check | Pass | Detail |", "|---|---|---|",
             f"| pytest: exit 0, ≥1 collected, no failure/error | {'yes' if pytest_ok(st) else '**NO**'} | "
             f"exit {st['returncode']}; {st['collected']} collected, {len(st['passed'])} passed, {len(st['failed'])} failed, "
             f"{len(st['errors'])} errors, {len(st['skipped'])} skipped |"]
    lines += [f"| {md(r['check'])} | {'yes' if r['pass'] else '**NO**'} | {md(r['detail'])} |" for r in ev]
    if st["skipped"]:
        lines += ["", "Skipped tests (not counted as passes): " + ", ".join(f"`{md(s)}`" for s in st["skipped"])]
    if st["failed"] or st["errors"]:
        lines += ["", "Failing tests: " + ", ".join(f"`{md(s)}`" for s in st["failed"] + st["errors"])]
    lines += ["", "## Cases", "", "| ID | Acceptance criterion | Evidence | Automated result | Actual | Owner sign-off |",
              "|---|---|---|---|---|---|"]
    lines += [f"| {r.id} | {md(r['acceptance criterion'])} | {md(r.evidence)} | {r['automated result']} | "
              f"{md(r.actual)} | {md(r['owner sign-off'])} |" for _, r in df.iterrows()]
    (S4 / "UAT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(df[["id", "automated result", "actual"]].to_string(index=False))
    if not pre_ok:
        print("UAT BLOCKED: preconditions failed (see outputs/stage4/UAT.md)", file=sys.stderr)
    return 0 if pre_ok and (auto["automated result"] == "PASS").all() else 1


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "src"))
    sys.exit(main())
