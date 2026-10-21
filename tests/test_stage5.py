"""Stage 5 backtest: each fold may use only labels and seller history known at its cut-off."""
import json

import pandas as pd
import pytest

import olist_analytics.run_stage5 as r5
from olist_analytics.gate import ReleaseBlocked

T, E = pd.Timestamp("2018-05-01"), pd.Timestamp("2018-06-01")


@pytest.fixture
def pop():
    rows = [  # id, purchase, delivered, late
        ("a", "2018-04-10", "2018-04-20", 0),   # known before T -> fit
        ("b", "2018-04-25", "2018-05-03", 1),   # purchased before T, delivered after T -> pending, NOT in fit
        ("c", "2018-05-02", "2018-05-12", 0),   # eval
        ("d", "2018-05-30", "2018-06-20", 1),   # eval (delivered after the block: label is final, fine for evaluation)
        ("e", "2018-06-01", "2018-06-05", 0),   # next block, not eval
    ]
    df = pd.DataFrame(rows, columns=["order_id", "order_purchase_timestamp", "order_delivered_customer_date", "is_late"])
    for c in ("order_purchase_timestamp", "order_delivered_customer_date"):
        df[c] = pd.to_datetime(df[c])
    return df


def test_fold_split_drops_labels_unknown_at_cutoff(pop):
    fit, ev, pending = r5.fold_split(pop, T, E)
    assert fit.order_id.tolist() == ["a"]
    assert pending.order_id.tolist() == ["b"]
    assert ev.order_id.tolist() == ["c", "d"]


def ok_meta(t):
    return [{"T": str(t), "max_label_delivery": None}]


def failing(rows):
    return [r["check"].split(": ", 1)[1] for r in rows if str(r["expected"]) != str(r["actual"])]


def test_clean_fold_passes_all_checks(pop):
    fit, ev, _ = r5.fold_split(pop, T, E)
    assert failing(r5.fold_checks("f", fit, ev, T, E, ok_meta("2018-04-01"), ok_meta(T))) == []


def test_leaked_future_label_in_fit_is_caught(pop):
    fit, ev, pending = r5.fold_split(pop, T, E)
    leaked = pd.concat([fit, pending])                        # 'b' delivered after T sneaks into the fit
    assert "fit uses only labels delivered before T" in failing(r5.fold_checks("f", leaked, ev, T, E, ok_meta(T), ok_meta(T)))


def test_eval_row_outside_block_is_caught(pop):
    fit, _, _ = r5.fold_split(pop, T, E)
    ev = pop[pop.order_id.isin(["c", "e"])]
    assert "eval purchases inside [T, T+1 month)" in failing(r5.fold_checks("f", fit, ev, T, E, ok_meta(T), ok_meta(T)))


def test_seller_snapshot_with_label_after_its_time_is_caught(pop):
    fit, ev, _ = r5.fold_split(pop, T, E)
    bad = [{"T": str(T), "max_label_delivery": "2018-05-03"}]
    assert "every seller snapshot holds only labels delivered before its T" in failing(
        r5.fold_checks("f", fit, ev, T, E, ok_meta("2018-04-01"), bad))


def test_eval_snapshot_refreshed_inside_month_is_caught(pop):
    fit, ev, _ = r5.fold_split(pop, T, E)
    refreshed = ok_meta(T) + ok_meta("2018-05-15")
    assert "eval seller snapshot frozen at T" in failing(r5.fold_checks("f", fit, ev, T, E, ok_meta(T), refreshed))


def test_eval_order_also_in_fit_is_caught(pop):
    fit, ev, _ = r5.fold_split(pop, T, E)
    assert "no eval order in the fit" in failing(r5.fold_checks("f", pd.concat([fit, ev]), ev, T, E, ok_meta(T), ok_meta(T)))


def test_reproduction_check_fails_on_different_scores_or_missing_rows():
    s3 = pd.DataFrame({"order_id": ["x", "y"], "p_logistic": [.1, .2], "p_gbm": [.3, .4]})
    assert r5.reproduces_stage3(s3.copy(), s3)[0]
    changed = s3.assign(p_gbm=[.3, .41])
    assert not r5.reproduces_stage3(changed, s3)[0]
    extra = pd.concat([s3, pd.DataFrame({"order_id": ["z"], "p_logistic": [.1], "p_gbm": [.1]})])
    assert not r5.reproduces_stage3(extra, s3)[0]


def test_failed_precondition_blocks_stage5_and_publishes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(r5, "REPORT", tmp_path / "stage5_backtest_report.md")
    monkeypatch.setattr(r5, "S5", tmp_path / "stage5")
    monkeypatch.setattr(r5, "preconditions", lambda: [{"check": "independent verification is bound to the current stage-3 files",
                                                       "expected": True, "actual": False}])
    (tmp_path / "stage5_backtest_report.md").write_text("old")
    with pytest.raises(ReleaseBlocked):
        r5.main()
    assert not (tmp_path / "stage5_backtest_report.md").exists()
    assert json.loads((tmp_path / "stage5" / "qa" / "RELEASE_BLOCKED.json").read_text())[0]["check"].startswith("independent")
