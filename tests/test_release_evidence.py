"""scripts/release_evidence.py must fail the release when any automated check fails, and never sign owner cases.
Self-contained: builds a small synthetic tree, so it never depends on (or skips for) a completed pipeline run."""
import csv
import hashlib
import importlib.util
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load():
    spec = importlib.util.spec_from_file_location("release_evidence", ROOT / "scripts" / "release_evidence.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def write_uat(root, results):
    p = root / "outputs/stage4/uat_results.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "acceptance criterion", "evidence", "automated result", "actual", "owner sign-off"])
        for i, res in results:
            w.writerow([i, "c", "e", res, "a", ""])


@pytest.fixture
def tree(tmp_path):
    cfg = tmp_path / "config" / "date_policy.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("seed: 1\n")
    s7 = tmp_path / "outputs" / "stage7"
    (s7 / "monitoring").mkdir(parents=True)
    (s7 / "PREREGISTRATION_SHA256.txt").write_text(hashlib.sha256(cfg.read_bytes()).hexdigest() + "  config/date_policy.yaml\n")
    with open(s7 / "policy_results.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["target", "policy", "coverage", "mean_promised_days"])
        for t, p in [("0.90", "B0_state_quantile"), ("0.90", "Q2_qr_conformal_A"), ("0.90", "Olist_promise"),
                     ("olist_matched", "B0_state_quantile")]:
            w.writerow([t, p, 0.9, 20.0])
    nom = {"single_week_llr": {"arl_weeks": 261.3}, "threshold": {"arl_weeks": 2e15}}
    (s7 / "monitoring" / "monitoring.json").write_text(json.dumps({"nominal_in_control_arl": {"B0_0.90": nom}}))
    write_uat(tmp_path, [("UAT-01", "PASS"), ("UAT-12", "PASS"), ("UAT-13", "n/a — owner review")])
    logs = tmp_path / "release" / "logs"
    logs.mkdir(parents=True)
    for f in ("run_all.log", "pytest.log", "ui_check.log", "build_uat.log"):
        (logs / f).write_text("ok\n")
    (logs / "pytest_junit.xml").write_text("<testsuites><testsuite tests='3' failures='0' errors='0' skipped='0'/></testsuites>")
    return tmp_path


def test_clean_tree_passes_and_leaves_owner_cases_open(tree):
    assert load().main("t", root=tree) == 0
    text = (tree / "release" / "RELEASE.md").read_text()
    assert "## Gate: PASS" in text
    assert "UAT-13" in text.split("owner cases still open")[1].splitlines()[0]
    assert (tree / "release" / "MANIFEST.sha256").exists()


def test_failed_automated_uat_fails_the_gate(tree):
    write_uat(tree, [("UAT-01", "FAIL"), ("UAT-12", "PASS"), ("UAT-13", "n/a — owner review")])
    assert load().main("t", root=tree) == 1
    assert "automated UAT not PASS: UAT-01" in (tree / "release" / "RELEASE.md").read_text()


def test_block_marker_failed_tests_missing_log_or_changed_config_fail_the_gate(tree):
    mod = load()
    marker = tree / "outputs" / "stage7" / "qa" / "RELEASE_BLOCKED.json"
    marker.parent.mkdir()
    marker.write_text("[]")
    assert mod.main("t", root=tree) == 1
    marker.unlink()
    junit = tree / "release" / "logs" / "pytest_junit.xml"
    good = junit.read_text()
    junit.write_text("<testsuite tests='3' failures='1' errors='0'/>")
    assert mod.main("t", root=tree) == 1
    junit.write_text(good)
    (tree / "release" / "logs" / "ui_check.log").unlink()
    assert mod.main("t", root=tree) == 1
    (tree / "release" / "logs" / "ui_check.log").write_text("ok\n")
    assert mod.main("t", root=tree) == 0
    (tree / "config" / "date_policy.yaml").write_text("seed: 2\n")
    assert mod.main("t", root=tree) == 1
