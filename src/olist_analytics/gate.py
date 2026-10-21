"""Release lifecycle shared by every stage: retire the current report at run start,
publish only when every blocking check passes, otherwise leave a block marker."""
from __future__ import annotations

import json

import pandas as pd


class ReleaseBlocked(SystemExit):
    pass


def release_gate(checks: pd.DataFrame, report_path, reraise: bool = True, blocked_path=None) -> None:
    """Block the formal report when any blocking check fails.

    On failure: write qa/RELEASE_BLOCKED.json, remove any previous report so a stale
    'passing' version cannot be mistaken for this run, and exit non-zero."""
    blocked = blocked_path or report_path.parent / "qa" / "RELEASE_BLOCKED.json"
    bad = checks[~checks["pass"].astype(bool)]
    if bad.empty:
        if blocked.exists():
            blocked.unlink()
        return
    blocked.parent.mkdir(parents=True, exist_ok=True)
    blocked.write_text(json.dumps(bad.to_dict(orient="records"), indent=2, default=str), encoding="utf-8")
    if report_path.exists():
        report_path.unlink()
    if reraise:
        raise ReleaseBlocked(f"Release blocked: {len(bad)} check(s) failed. See {blocked}.")


def retire_current_report(report_path) -> None:
    """At run start the previous report stops being 'current': it is moved to
    outputs/history/ with a SUPERSEDED banner. Only a fully passing run writes a new one."""
    if not report_path.exists():
        return
    hist = report_path.parent / "history"
    hist.mkdir(parents=True, exist_ok=True)
    stamp = pd.Timestamp(report_path.stat().st_mtime, unit="s").strftime("%Y%m%dT%H%M%S")
    text = report_path.read_text(encoding="utf-8")
    (hist / f"SUPERSEDED_{stamp}_{report_path.name}").write_text(
        "> SUPERSEDED — historical copy, not the current release.\n\n" + text, encoding="utf-8")
    report_path.unlink()




STAGE4_OUTPUTS = ("weekly_review.html", "data_quality.html", "model_report.html",
                  "stage4/lineage.json", "stage4/stage4_checks.csv",
                  "stage4/ui_checks.csv", "stage4/ui_evidence.json", "stage4/UI_CHECKS.md",
                  "stage4/uat_results.csv", "stage4/UAT.md")


def retire_stage4_outputs(out) -> None:
    """The three pages and every piece of evidence about them (UI checks, UAT) stop being current
    together: rerunning any upstream stage, or stage 4 itself, must not leave old evidence beside new pages."""
    for rel in STAGE4_OUTPUTS:
        retire_current_report(out / rel)
