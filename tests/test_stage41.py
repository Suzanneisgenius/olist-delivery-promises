"""v0.4.1 fail-closed fixes: full independent metric check, refresh order, UAT bound to current evidence."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from olist_analytics import run_all
from olist_analytics.gate import STAGE4_OUTPUTS, retire_stage4_outputs

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


verify = load_script("verify_stage3")
uat = load_script("build_uat")


# ------------------------------------------------------------------ independent verification
@pytest.fixture
def scored():
    rng = np.random.default_rng(0)
    n = 400
    y = (rng.random(n) < 0.1).astype(int)
    pred = pd.DataFrame({"order_id": [f"o{i}" for i in range(n)],
                         "purchase_week": np.repeat(["2018-04-02", "2018-04-09", "2018-04-16", "2018-04-23"], n // 4),
                         "y": y, "p_baseline": 0.08, "p_logistic": np.clip(0.05 + 0.3 * y + rng.normal(0, .1, n), 0, 1),
                         "p_gbm": rng.random(n)})
    ind = verify.recompute(pred, seed=1)
    metrics = pd.DataFrame([{"model": m, "prevalence": v["late"] / v["n"], **v} for m, v in ind.items()])
    return pred, ind, metrics


def test_verifier_metrics_agree_with_sklearn(scored):
    from sklearn.metrics import average_precision_score, roc_auc_score
    pred, ind, _ = scored
    assert np.isclose(ind["logistic"]["average_precision"], average_precision_score(pred.y, pred.p_logistic))
    assert np.isclose(ind["gbm"]["roc_auc"], roc_auc_score(pred.y, pred.p_gbm))


def test_consistent_metrics_have_no_mismatch(scored):
    _, ind, metrics = scored
    assert verify.compare(ind, metrics) == []


def test_auc_changed_to_one_is_caught_even_though_ap_is_unchanged(scored):
    _, ind, metrics = scored
    metrics.loc[metrics.model == "logistic", "roc_auc"] = 1.0
    assert any(b.startswith("logistic.roc_auc") for b in verify.compare(ind, metrics))


def test_recall_changed_while_hits_kept_is_caught_twice(scored):
    _, ind, metrics = scored
    metrics.loc[metrics.model == "logistic", "recall_at_top"] = 1.0
    bad = verify.compare(ind, metrics)
    assert any("logistic.recall_at_top" in b for b in bad)
    assert any("identity recall_at_top = hits/late" in b for b in bad)


def test_non_headline_model_is_checked(scored):
    _, ind, metrics = scored
    metrics.loc[metrics.model == "gbm", "brier"] += 0.01
    assert any(b.startswith("gbm.brier") for b in verify.compare(ind, metrics))


def test_missing_model_row_is_a_mismatch(scored):
    _, ind, metrics = scored
    assert any("baseline: missing" in b for b in verify.compare(ind, metrics[metrics.model != "baseline"]))


def test_verifier_failure_removes_old_evidence_and_exits_nonzero(tmp_path):
    s3 = tmp_path / "outputs" / "stage3"
    s3.mkdir(parents=True)
    (s3 / "independent_verification.json").write_text('{"all_match": true}')   # left over from an older run
    assert verify.main(tmp_path) == 1
    assert not (s3 / "independent_verification.json").exists()
    assert (s3 / "qa" / "VERIFY_FAILED.json").exists()


# ------------------------------------------------------------------ refresh order
def test_refresh_order_puts_independent_verification_between_stage3_and_stage4():
    assert [n for n, _ in run_all.STEPS] == ["stage 1", "stage 2", "stage 3", "independent verification", "stage 4",
                                                 "stage 5 (backtest)", "stage 7 (date policy)",
                                                 "stage 7 part 3 (monitoring)"]


def test_failed_verification_stops_before_stage4(monkeypatch):
    calls = []
    class R:
        returncode = 1
    monkeypatch.setattr(run_all.subprocess, "run", lambda *a, **k: R())
    steps = [("stage 3", lambda: calls.append("stage 3")), ("independent verification", run_all.verify_stage3),
             ("stage 4", lambda: calls.append("stage 4"))]
    with pytest.raises(run_all.VerificationFailed):
        run_all.main(steps)
    assert calls == ["stage 3"]


def test_verifier_runs_isolated_from_project_modules(monkeypatch):
    seen = {}
    class R:
        returncode = 0
    monkeypatch.setattr(run_all.subprocess, "run", lambda cmd, **k: seen.setdefault("cmd", cmd) and R())
    run_all.verify_stage3()
    assert "-I" in seen["cmd"] and seen["cmd"][-1].endswith("verify_stage3.py")


# ------------------------------------------------------------------ retirement of stale evidence
def test_upstream_rerun_retires_pages_and_their_ui_uat_evidence(tmp_path):
    (tmp_path / "stage4").mkdir()
    for rel in STAGE4_OUTPUTS:
        (tmp_path / rel).write_text("old")
    retire_stage4_outputs(tmp_path)
    assert not any((tmp_path / rel).exists() for rel in STAGE4_OUTPUTS)
    assert (tmp_path / "stage4" / "history").exists()


# ------------------------------------------------------------------ UAT: pytest fail-closed
def junit(tmp_path, cases):
    body = "".join(f'<testcase name="{n}">{"" if k == "passed" else f"<{k}/>"}</testcase>' for n, k in cases)
    p = tmp_path / "j.xml"
    p.write_text(f'<testsuites><testsuite errors="{sum(k == "error" for _, k in cases)}">{body}</testsuite></testsuites>')
    return p


def test_one_failing_regression_test_fails_uat_even_if_case_tests_pass(tmp_path):
    st = uat.parse_junit(junit(tmp_path, [("test_a", "passed"), ("test_unrelated", "failure")]), 1)
    assert not uat.pytest_ok(st) and st["failed"] == ["test_unrelated"]


def test_nonzero_pytest_exit_fails_uat_even_with_clean_report(tmp_path):
    assert not uat.pytest_ok(uat.parse_junit(junit(tmp_path, [("test_a", "passed")]), 2))


def test_zero_collected_tests_fails_uat(tmp_path):
    assert not uat.pytest_ok(uat.parse_junit(junit(tmp_path, []), 0))


def test_skipped_test_is_listed_and_not_counted_as_passed(tmp_path):
    st = uat.parse_junit(junit(tmp_path, [("test_a", "passed"), ("test_b", "skipped")]), 0)
    assert st["skipped"] == ["test_b"] and "test_b" not in st["passed"]


def test_markdown_cells_escape_pipes_and_newlines():
    assert uat.md("max |gap| < 1e-12\nnext") == "max \\|gap\\| < 1e-12 next"


# ------------------------------------------------------------------ UAT: owner sign-off is never written
def test_signoff_file_is_not_overwritten_and_other_release_is_stale(tmp_path):
    p = tmp_path / "owner_signoff.csv"
    p.write_text("id,release_sha256,reviewer,date,decision,note\nUAT-14,aaaa1111,Owner,2026-10-20,accept,\n")
    before = p.read_text()
    shown = uat.read_signoff(p, "bbbb2222")
    assert p.read_text() == before
    assert shown["UAT-14"].startswith("stale")
    assert uat.read_signoff(p, "aaaa1111")["UAT-14"].startswith("accept")


def test_missing_signoff_file_gets_header_only(tmp_path):
    p = tmp_path / "uat" / "owner_signoff.csv"
    assert uat.read_signoff(p, "x") == {}
    assert p.read_text().strip() == "id,release_sha256,reviewer,date,decision,note"


# ------------------------------------------------------------------ UAT: evidence bound to the current pages
@pytest.fixture
def release(tmp_path, monkeypatch):
    out = tmp_path
    (out / "stage4").mkdir()
    for n in uat.PAGE_KEYS.values():
        (out / n).write_text(f"page {n}")
    pages = {k: uat.sha(out / n) for k, n in uat.PAGE_KEYS.items()}
    (out / "stage4" / "lineage.json").write_text(json.dumps({"pages": pages, "checks_pass": True}))
    (out / "stage4" / "ui_checks.csv").write_text("case,pass\nx,True\n")
    (out / "stage4" / "ui_evidence.json").write_text(json.dumps({
        "pages_sha256": {n: uat.sha(out / n) for n in uat.PAGE_KEYS.values()},
        "stage4_lineage_sha256": uat.sha(out / "stage4" / "lineage.json"),
        "ui_checks_sha256": uat.sha(out / "stage4" / "ui_checks.csv"), "checks_pass": True}))
    from olist_analytics import run_stage4
    monkeypatch.setattr(run_stage4, "verification_status", lambda: [{"check": "verification", "actual": True}])
    return out


def bad(rows):
    return [r["check"] for r in rows if not r["pass"]]


def test_current_evidence_passes(release):
    assert bad(uat.evidence_status(release)) == []


def test_ui_evidence_from_older_pages_is_rejected(release):
    (release / "model_report.html").write_text("republished page")
    lin = json.loads((release / "stage4" / "lineage.json").read_text())
    lin["pages"]["model"] = uat.sha(release / "model_report.html")
    (release / "stage4" / "lineage.json").write_text(json.dumps(lin))
    b = bad(uat.evidence_status(release))
    assert "browser evidence was produced on these exact pages" in b
    assert "browser evidence belongs to the current stage-4 release" in b


def test_page_edited_after_release_is_rejected(release):
    (release / "weekly_review.html").write_text("hand edit")
    assert "pages on disk == pages of the stage-4 release" in bad(uat.evidence_status(release))


def test_blocked_stage4_is_rejected(release):
    (release / "stage4" / "qa").mkdir()
    (release / "stage4" / "qa" / "RELEASE_BLOCKED.json").write_text("[]")
    assert "stage 4 is not blocked" in bad(uat.evidence_status(release))


def test_failing_browser_evidence_is_rejected(release):
    ev = json.loads((release / "stage4" / "ui_evidence.json").read_text())
    ev["checks_pass"] = False
    (release / "stage4" / "ui_evidence.json").write_text(json.dumps(ev))
    assert "browser evidence: all checks passed" in bad(uat.evidence_status(release))
