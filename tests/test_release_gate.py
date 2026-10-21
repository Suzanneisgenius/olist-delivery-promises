"""A single failing blocking check must stop the formal report."""
import json

import pandas as pd
import pytest

from olist_analytics.run_stage1 import ReleaseBlocked, release_gate


def checks(ok=True):
    return pd.DataFrame([{"check": "a", "expected": 1, "actual": 1, "pass": True},
                         {"check": "SQL cells", "expected": 373, "actual": 373 if ok else 372, "pass": ok}])


def test_injected_failure_blocks_and_removes_stale_report(tmp_path):
    report = tmp_path / "stage1_quality_report.md"
    report.write_text("old passing report")
    with pytest.raises(ReleaseBlocked) as e:
        release_gate(checks(ok=False), report)
    assert e.value.code != 0
    assert not report.exists()
    blocked = json.loads((tmp_path / "qa" / "RELEASE_BLOCKED.json").read_text())
    assert blocked[0]["check"] == "SQL cells"


def test_all_pass_clears_old_block_marker(tmp_path):
    (tmp_path / "qa").mkdir()
    (tmp_path / "qa" / "RELEASE_BLOCKED.json").write_text("[]")
    release_gate(checks(ok=True), tmp_path / "stage1_quality_report.md")
    assert not (tmp_path / "qa" / "RELEASE_BLOCKED.json").exists()


# ---------------------------------------------------------------- whole-run lifecycle
import olist_analytics.run_stage1 as rs
from olist_analytics.report import readiness


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    out = tmp_path / "outputs"
    (out / "qa").mkdir(parents=True)
    monkeypatch.setattr(rs, "OUT", out)
    monkeypatch.setattr(rs, "QA", out / "qa")
    monkeypatch.setattr(rs, "MARTS", out / "marts")
    monkeypatch.setattr(rs, "REPORT", out / "stage1_quality_report.md")
    monkeypatch.setattr(rs, "source_manifest", lambda: pd.DataFrame())
    monkeypatch.setattr(rs, "load_all", lambda: {})
    monkeypatch.setattr(rs, "CONTRACT", {})
    (out / "stage1_quality_report.md").write_text("previous PASSING report — Approved for stage 2")
    return out


def test_hard_contract_failure_leaves_no_current_passing_report(sandbox, monkeypatch):
    fail = pd.DataFrame([{"table": "orders", "check": "unique key (order_id)", "violations": 3,
                          "rows": 10, "status": "FAIL", "policy": "hard", "detail": ""}])
    monkeypatch.setattr(rs, "check_contract", lambda t, raw: fail)
    with pytest.raises(rs.ReleaseBlocked):
        rs.main()
    assert not (sandbox / "stage1_quality_report.md").exists()
    assert (sandbox / "qa" / "RELEASE_BLOCKED.json").exists()
    hist = list((sandbox / "history").glob("SUPERSEDED_*"))
    assert len(hist) == 1 and hist[0].read_text().startswith("> SUPERSEDED")


def test_unexpected_error_is_also_a_blocked_release(sandbox, monkeypatch):
    def boom(t, raw):
        raise ValueError("disk full")
    monkeypatch.setattr(rs, "check_contract", boom)
    with pytest.raises(ValueError):
        rs.main()
    assert not (sandbox / "stage1_quality_report.md").exists()
    assert "disk full" in (sandbox / "qa" / "RELEASE_BLOCKED.json").read_text()


def test_no_window_is_never_ready():
    assert readiness({"status": "NO_QUALIFYING_WINDOW"})[0] == "NOT_READY"


def test_window_different_from_approval_needs_re_approval():
    sel = {"status": "OK", "first_week": "2017-02-27", "last_week": "2018-07-09", "weeks": 72}
    assert readiness(sel)[0] == "NEEDS_RE_APPROVAL"
    sel.update(last_week="2018-07-23", weeks=74)
    assert readiness(sel)[0] == "READY"


# ---------------------------------------------------------------- independent classifier
def raw(**kw):
    base = {"order_status": "delivered", "order_purchase_timestamp": "2018-03-01 10:00:00",
            "order_delivered_customer_date": "2018-03-09 08:00:00", "order_estimated_delivery_date": "2018-03-08 00:00:00"}
    base.update(kw)
    return base


def test_classifier_matches_mart_rule_order():
    assert rs.classify_raw_order(raw()) == ("L", 1)
    assert rs.classify_raw_order(raw(order_estimated_delivery_date="2018-02-27 00:00:00")) == ("NO_VALID_ESTIMATE", None)
    assert rs.classify_raw_order(raw(order_estimated_delivery_date="")) == ("NO_VALID_ESTIMATE", None)
    assert rs.classify_raw_order(raw(order_status="canceled")) == ("X", None)
    assert rs.classify_raw_order(raw(order_delivered_customer_date="")) == ("U", None)
