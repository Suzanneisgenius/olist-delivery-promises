"""Stage 2 refuses to run on a blocked or not-ready stage-1 release."""
import json

import pandas as pd
import pytest

import olist_analytics.run_stage2 as r2
from olist_analytics.gate import ReleaseBlocked


@pytest.fixture
def out(tmp_path, monkeypatch):
    (tmp_path / "qa").mkdir()
    monkeypatch.setattr(r2, "OUT", tmp_path)
    monkeypatch.setattr(r2, "REPORT", tmp_path / "stage2_analysis.md")
    return tmp_path


def facts(status="OK", first="2017-02-27", last="2018-07-23", weeks=74):
    return {"cohort_proposal": {"selected": {"status": status, "first_week": first, "last_week": last, "weeks": weeks}}}


def test_blocked_stage1_blocks_stage2(out):
    (out / "stage1_quality_report.md").write_text("x")
    (out / "qa" / "stage1_facts.json").write_text(json.dumps(facts()))
    (out / "qa" / "RELEASE_BLOCKED.json").write_text("[]")
    with pytest.raises(ReleaseBlocked):
        r2.preconditions()


def test_window_mismatch_blocks_stage2(out):
    (out / "stage1_quality_report.md").write_text("x")
    (out / "qa" / "stage1_facts.json").write_text(json.dumps(facts(last="2018-07-09", weeks=72)))
    with pytest.raises(ReleaseBlocked):
        r2.preconditions()
    assert (out / "stage2" / "qa" / "RELEASE_BLOCKED.json").exists()
    assert not (out / "qa" / "RELEASE_BLOCKED.json").exists()


def test_ready_stage1_passes(out):
    (out / "stage1_quality_report.md").write_text("x")
    (out / "qa" / "stage1_facts.json").write_text(json.dumps(facts()))
    assert r2.preconditions()["cohort_proposal"]["selected"]["weeks"] == 74


def test_stage2_failure_does_not_block_retry_on_ready_stage1(out):
    (out / "stage1_quality_report.md").write_text("valid stage1")
    (out / "qa" / "stage1_facts.json").write_text(json.dumps(facts()))
    with pytest.raises(ReleaseBlocked):
        r2.release_gate(pd.DataFrame([{"check":"SQL", "pass":False}]), out/"stage2_analysis.md")
    assert not (out / "qa" / "RELEASE_BLOCKED.json").exists()
    assert r2.preconditions()["cohort_proposal"]["selected"]["weeks"] == 74


# ---------------------------------------------------------------- stage 3 uses the same entry rule
import olist_analytics.run_stage3 as r3


def test_stage3_refuses_a_blocked_stage1(tmp_path, monkeypatch):
    (tmp_path / "qa").mkdir()
    monkeypatch.setattr(r3, "OUT", tmp_path)
    monkeypatch.setattr(r3, "S3", tmp_path / "stage3")
    monkeypatch.setattr(r3, "REPORT", tmp_path / "stage3_model_report.md")
    (tmp_path / "stage1_quality_report.md").write_text("x")
    (tmp_path / "qa" / "stage1_facts.json").write_text(json.dumps(facts(last="2018-07-09", weeks=72)))
    with pytest.raises(ReleaseBlocked):
        r3.preconditions()
    assert (tmp_path / "stage3" / "qa" / "RELEASE_BLOCKED.json").exists()
    assert not (tmp_path / "qa" / "RELEASE_BLOCKED.json").exists()     # stage-1 status not touched
