"""Stage 7: promised-date policies, conformal shift, scoring and the registered decision rules."""
import numpy as np
import pandas as pd
import pytest

import olist_analytics.run_stage7 as r7
from olist_analytics.date_policy import (apply_state_policy, conformal_shift, monthly_unreliable, score,
                                         state_quantile_policy, to_promise, verdict_complex_over_baseline)
from olist_analytics.gate import ReleaseBlocked


def test_conformal_shift_is_the_right_order_statistic():
    req, pred = np.arange(1, 10), np.zeros(9)          # scores 1..9, n = 9
    assert conformal_shift(req, pred, 0.5) == 5.0      # ceil(10 * 0.5) = 5th smallest
    assert conformal_shift(req, pred, 0.9) == 9.0      # ceil(10 * 0.9) = 9th smallest


def test_conformal_shift_is_infinite_when_calibration_is_too_small():
    assert conformal_shift(np.arange(5), np.zeros(5), 0.95) == float("inf")   # ceil(6 * .95) = 6 > 5


def test_conformal_promise_reaches_nominal_coverage_on_exchangeable_data():
    rng = np.random.default_rng(0)
    cover = []
    for _ in range(200):
        y = rng.lognormal(2.3, 0.5, 1200).round()
        cal, test = y[:200], y[200:]
        s = conformal_shift(cal, np.full(200, 8.0), 0.9)
        cover.append((test <= np.ceil(8.0 + s)).mean())
    assert np.mean(cover) >= 0.895                      # marginal guarantee (>= level, up to simulation noise)


def test_promises_are_whole_days_and_at_least_one():
    assert to_promise(np.array([0.2, 3.0, 3.0001, 7.5])).tolist() == [1, 3, 4, 8]


def test_state_policy_falls_back_to_overall_for_small_states():
    req = pd.Series([1, 2, 3, 4, 5, 10, 10, 10])
    st = pd.Series(["A"] * 5 + ["B"] * 3)
    pol = state_quantile_policy(req, st, 0.5, min_n=4)
    assert pol["by_state"] == {"A": 3.0} and "B" not in pol["by_state"]
    assert apply_state_policy(pol, pd.Series(["A", "B", "C"])).tolist() == [3, int(pol["overall"]), int(pol["overall"])]


def test_score_uses_the_project_on_time_rule():
    s = score(pd.Series([5, 6, 7, 10]), pd.Series([6, 6, 6, 6]))          # 7 and 10 are late
    assert s["coverage"] == 0.5 and s["mean_overrun_days_when_missed"] == 2.5 and s["mean_promised_days"] == 6


@pytest.mark.parametrize("cx_days,cx_cov,keep", [(19.0, 0.93, True), (19.5, 0.94, False), (19.0, 0.929, False), (18.0, 0.95, True)])
def test_registered_rule_needs_one_day_shorter_and_at_most_one_point_lower(cx_days, cx_cov, keep):
    base = {"mean_promised_days": 20.0, "coverage": 0.94}
    assert verdict_complex_over_baseline({"mean_promised_days": cx_days, "coverage": cx_cov}, base)["keep_complex"] is keep


def test_monthly_reliability_flags_only_large_months_far_below_target():
    m = pd.DataFrame({"month": ["2018-04", "2018-05", "2018-07"], "orders": [6000, 6000, 900],
                      "coverage": [0.885, 0.86, 0.80]})
    assert monthly_unreliable(m, 0.90) == ["2018-05"]    # July is too small to judge, April is within 3 pts


@pytest.fixture
def pop():
    rows = [  # purchase, delivered
        ("2017-08-01", "2017-08-10"),   # fit
        ("2017-11-01", "2017-11-12"),   # calibration A
        ("2018-02-01", "2018-02-15"),   # calibration B
        ("2018-03-25", "2018-04-05"),   # calibration B window but delivered AFTER the freeze -> excluded
        ("2018-04-03", "2018-04-12"),   # evaluation
    ]
    df = pd.DataFrame(rows, columns=["order_purchase_timestamp", "order_delivered_customer_date"]).apply(pd.to_datetime)
    df["order_id"] = [f"o{i}" for i in range(len(df))]
    return df


def test_split_rows_uses_only_labels_known_at_the_freeze(pop):
    cfg = r7.load_yaml("date_policy.yaml")
    s = r7.split_rows(pop, cfg)
    assert s["fit"].order_id.tolist() == ["o0"] and s["cal_A"].order_id.tolist() == ["o1"]
    assert s["cal_B"].order_id.tolist() == ["o2"]                       # o3 not known at 2018-04-01
    assert s["eval"].order_id.tolist() == ["o4"]


def test_changed_config_blocks_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr(r7, "REPORT", tmp_path / "stage7_date_policy_report.md")
    monkeypatch.setattr(r7, "S7", tmp_path / "stage7")
    monkeypatch.setattr(r7, "MONITOR_REPORT", tmp_path / "stage7_monitoring_report.md")   # never touch real outputs
    monkeypatch.setattr(r7, "registered_sha", lambda: "0" * 64)          # config no longer matches the registration
    with pytest.raises(ReleaseBlocked):
        r7.main()
    assert (tmp_path / "stage7" / "qa" / "RELEASE_BLOCKED.json").exists()
    assert not (tmp_path / "stage7_date_policy_report.md").exists()


def test_state_quantile_is_the_empirical_inverse_cdf():
    assert state_quantile_policy(pd.Series([1, 2]), pd.Series(["A", "A"]), 0.5, 1)["overall"] == 1.0   # 1 covers half
    rng = np.random.default_rng(4)
    for n in (3, 7, 20, 101):
        x = rng.integers(1, 40, n)
        for q in (0.5, 0.9, 0.95):
            d = state_quantile_policy(pd.Series(x), pd.Series(["A"] * n), q, 1)["overall"]
            assert d == np.sort(x)[int(np.ceil(n * q)) - 1]
            assert (x <= d).mean() >= q and (d == x.min() or (x <= d - 1).mean() < q)


def test_infinite_shift_cannot_become_a_promise():
    with pytest.raises(ValueError):
        to_promise(np.array([5.0]) + conformal_shift(np.arange(5), np.zeros(5), 0.95))


def test_rule_edges_survive_floating_point():
    base = {"mean_promised_days": 20.0, "coverage": 0.94}
    assert verdict_complex_over_baseline({"mean_promised_days": 19.0, "coverage": 0.94 - 0.01}, base)["keep_complex"]
