"""Stage 4 publishes only on current, consistent upstream releases; links and embedded data are checked."""
import json

import pandas as pd
import pytest

import olist_analytics.run_stage4 as r4
from olist_analytics.dashboard import rebase_links
from olist_analytics.gate import ReleaseBlocked
from olist_analytics.site import nav, page


def test_rebase_links_prefixes_relative_targets_only():
    html = '<a href="lineage.json">x</a><a href="../qa/m.csv">y</a><a href="https://a.b">z</a><a href="#top">t</a>'
    out = rebase_links(html, "stage2/")
    assert 'href="stage2/lineage.json"' in out and 'href="qa/m.csv"' in out
    assert 'href="https://a.b"' in out and 'href="#top"' in out


def test_nav_marks_only_the_current_page():
    n = nav("model_report.html")
    assert n.count("aria-current") == 1 and 'href="model_report.html" aria-current' in n


def test_embedded_page_data_round_trips_including_angle_brackets():
    data = {"note": "a < b", "x": 1.5}
    assert r4.embedded(page("t", "data_quality.html", "<p>x</p>", data), "page-data") == data


def test_broken_local_link_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(r4, "OUT", tmp_path)
    (tmp_path / "ok.csv").write_text("a")
    bad = r4.broken_links('<a href="ok.csv">1</a><a href="missing.csv">2</a><a href="model_report.html">3</a>')
    assert bad == ["missing.csv"]


@pytest.fixture
def upstream(tmp_path, monkeypatch):
    out = tmp_path
    for d in ("qa", "stage2/qa", "stage3/qa", "marts", "stage4/qa"):
        (out / d).mkdir(parents=True, exist_ok=True)
    (out / "marts" / "orders_mart.csv").write_text("order_id\no1\n")
    (out / "qa" / "stage1_facts.json").write_text(json.dumps({"source_manifest": []}))
    from olist_analytics.io import sha256
    mart, facts = sha256(out / "marts" / "orders_mart.csv"), sha256(out / "qa" / "stage1_facts.json")
    (out / "stage2" / "lineage.json").write_text(json.dumps({"mart_sha256": mart, "stage1_facts_sha256": facts, "checks_pass": True}))
    (out / "stage3" / "lineage.json").write_text(json.dumps({"mart_sha256": mart, "checks_pass": True}))
    for f in ("stage1_quality_report.md", "stage2_analysis.md", "stage3_model_report.md"):
        (out / f).write_text("x")
    for f in ("stage3/test_predictions.csv", "stage3/test_metrics.csv", "stage3/stage3_checks.csv", "qa/source_manifest.csv"):
        (out / f).write_text("a\n1\n")
    monkeypatch.setattr(r4, "OUT", out)
    monkeypatch.setattr(r4, "S2", out / "stage2")
    monkeypatch.setattr(r4, "S3", out / "stage3")
    monkeypatch.setattr(r4, "BLOCK", out / "stage4" / "qa" / "RELEASE_BLOCKED.json")
    monkeypatch.setattr(r4, "PAGES", {k: out / v.name for k, v in r4.PAGES.items()})
    write_verification(out)
    return out


def write_verification(out, all_match=True):
    from olist_analytics.io import sha256
    (out / "stage3" / "independent_verification.json").write_text(json.dumps(
        {"all_match": all_match, "bound_sha256": {k: sha256(f) for k, f in r4.bound_files().items()}}))


def failed(rows):
    return [r["check"] for r in rows if not r["actual"]]


def test_consistent_upstream_passes_preconditions(upstream):
    assert failed(r4.preconditions()) == []


def test_blocked_stage3_blocks_stage4(upstream):
    (upstream / "stage3" / "qa" / "RELEASE_BLOCKED.json").write_text("[]")
    assert "stage 3 is not blocked" in failed(r4.preconditions())


def test_stage3_built_on_another_mart_blocks_stage4(upstream):
    (upstream / "stage3" / "lineage.json").write_text(json.dumps({"mart_sha256": "other", "checks_pass": True}))
    assert "stage 3 built on the current mart" in failed(r4.preconditions())


def test_failed_precondition_publishes_nothing(upstream):
    (upstream / "stage2_analysis.md").unlink()
    (upstream / "model_report.html").write_text("old page")
    with pytest.raises(ReleaseBlocked):
        r4.main()
    assert not (upstream / "model_report.html").exists()
    assert (upstream / "stage4" / "qa" / "RELEASE_BLOCKED.json").exists()


def test_missing_independent_verification_blocks_stage4(upstream):
    (upstream / "stage3" / "independent_verification.json").unlink()
    assert "independent verification exists for this stage-3 run" in failed(r4.preconditions())


def test_verification_reporting_a_mismatch_blocks_stage4(upstream):
    write_verification(upstream, all_match=False)
    assert "independent verification reports all_match" in failed(r4.preconditions())


def test_stale_verification_blocks_stage4_when_predictions_change_after_it(upstream):
    (upstream / "stage3" / "test_predictions.csv").write_text("a\n2\n")       # new stage-3 output, old evidence
    assert "independent verification is bound to the current stage-3 files" in failed(r4.preconditions())


def test_stale_verification_blocks_stage4_when_metrics_change_after_it(upstream):
    (upstream / "stage3" / "test_metrics.csv").write_text("a\n0.99\n")
    assert "independent verification is bound to the current stage-3 files" in failed(r4.preconditions())
