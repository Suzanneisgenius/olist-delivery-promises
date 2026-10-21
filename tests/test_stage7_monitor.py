"""Stage 7 part 3: weekly cohorts, alarm rules, h calibration and the simulation harness."""
import numpy as np
import pandas as pd
import pytest

import olist_analytics.monitoring as mon
import olist_analytics.run_stage7_monitor as rm
from olist_analytics.gate import ReleaseBlocked


def test_weekly_cohorts_use_monday_weeks_and_finalise_after_the_largest_promise():
    ts = pd.Series(pd.to_datetime(["2018-05-14 10:00", "2018-05-20 23:00", "2018-05-21 01:00"]))   # Mon, Sun, next Mon
    w = mon.weekly_cohorts(ts, pd.Series([5, 12, 3]), pd.Series([10, 10, 4]))
    assert w.week.dt.strftime("%Y-%m-%d").tolist() == ["2018-05-14", "2018-05-21"]
    assert w.orders.tolist() == [2, 1] and w.misses.tolist() == [1, 0]
    # last purchase day (Sunday 20 May) + max promise 10 + 1: a miss is known the day after its promise date
    assert w.final_at.iloc[0] == pd.Timestamp("2018-05-31")


def test_cusum_weights_have_the_right_signs():
    a, b = mon.cusum_weights(0.10, 0.15)
    assert a > 0 > b and np.isclose(a, np.log(1.5))


def test_cusum_accumulates_and_resets_after_an_alarm():
    a, b = mon.cusum_weights(0.10, 0.15)
    stat, alarm = mon.cusum([3, 3, 0, 0], [10, 10, 10, 10], 0.10, 0.15, h=1.5)
    step = 3 * a + 7 * b
    assert np.isclose(stat[0], step) and not alarm[0]            # 0.86 < 1.5
    assert alarm[1] and np.isclose(stat[1], 2 * step)            # 1.72 > 1.5 -> alarm, then reset
    assert stat[2] == 0.0 and not alarm[2:].any()                # negative steps floor at zero


def test_threshold_rule_needs_two_consecutive_large_low_weeks():
    cov = [0.84, 0.84, 0.84, 0.84, 0.84, 0.90, 0.84, 0.84]
    n = [500, 500, 500, 500, 150, 500, 500, 500]
    assert mon.threshold_alarms(cov, n, 0.90).tolist() == [False, True, False, True, False, False, False, True]


def test_h_is_zero_when_the_registered_arl_is_unattainable():
    out = mon.calibrate_h(0.10, 0.15, 1200, 52, np.random.default_rng(0), runs=2000, cap=600)
    assert out["h"] == 0.0 and out["restricted_mean_run_length_weeks"] > 52


def test_h_hits_the_target_arl_when_it_is_attainable():
    out = mon.calibrate_h(0.10, 0.15, 50, 52, np.random.default_rng(0), runs=4000, cap=1000)
    assert out["h"] > 0 and abs(out["restricted_mean_run_length_weeks"] - 52) / 52 < 0.10   # ARL moves in steps (misses are counts)


@pytest.mark.parametrize("sc,week,m", [("none", 20, 1.0), ("sudden", 8, 1.0), ("sudden", 9, 1.2), ("gradual", 4, 1.0),
                                       ("gradual", 5, 1.02), ("gradual", 14, 1.2), ("transient", 10, 1.3),
                                       ("transient", 11, 1.0)])
def test_registered_scenarios(sc, week, m):
    assert np.isclose(mon.multiplier(sc, week), m)


def test_shifted_days_round_half_up():
    assert mon.shifted(np.array([10, 12, 25, 3]), 1.02).tolist() == [10, 12, 26, 3]   # 10.2, 12.24, 25.5, 3.06
    assert mon.shifted(np.array([5, 7]), 1.3).tolist() == [7, 9]                    # 6.5 -> 7, 9.1 -> 9


def _sim(promised, scenario="none"):
    req = np.full(100, 10)
    return mon.simulate(req, np.full(100, promised), scenario, p0=0.1, p1=0.15, h=0.0, target=0.9, weeks=12, n=300,
                        reps=20, rng=np.random.default_rng(1))


def test_simulation_never_alarms_when_every_order_is_covered():
    s = _sim(promised=30)
    assert s.coverage.eq(1).all() and not s.cusum_alarm.any() and not s.threshold_alarm.any()


def test_simulation_detects_a_sudden_shift_that_breaks_every_promise():
    s = _sim(promised=11, scenario="sudden")                     # 10 days fits; 12 days (x1.2) misses
    rows = mon.summarize(s, "sudden", 12)
    cus = next(r for r in rows if r["rule"] == "cusum")
    assert cus["false_alarms_per_year"] == 0 and cus["detected_share"] == 1 and cus["median_delay_weeks"] == 0
    thr = next(r for r in rows if r["rule"] == "threshold")
    assert thr["median_delay_weeks"] == 1                        # needs a second low week


def test_dispersion_ratio_is_near_one_for_binomial_weeks():
    rng = np.random.default_rng(3)
    n = np.full(400, 1000)
    m = rng.binomial(n, 0.08)
    w = pd.DataFrame({"orders": n, "misses": m, "coverage": 1 - m / n})
    assert 0.85 < mon.dispersion_ratio(w) < 1.15


def test_monitoring_is_blocked_without_a_parts_1_2_verdict(tmp_path, monkeypatch):
    s7 = tmp_path / "stage7"
    s7.mkdir()
    monkeypatch.setattr(rm, "S7", s7)
    monkeypatch.setattr(rm, "M", s7 / "monitoring")
    monkeypatch.setattr(rm, "REPORT", tmp_path / "stage7_monitoring_report.md")
    monkeypatch.setattr(rm, "PART12_REPORT", tmp_path / "missing.md")
    monkeypatch.setattr(rm, "registered_sha", lambda: rm.sha256(rm.CFG_PATH))
    with pytest.raises(ReleaseBlocked):
        rm.main()
    assert (s7 / "monitoring" / "qa" / "RELEASE_BLOCKED.json").exists()
    assert not (tmp_path / "stage7_monitoring_report.md").exists()


def test_h0_cusum_never_carries_evidence_across_weeks():
    rng = np.random.default_rng(5)
    n = np.full(300, 1200)
    m = rng.binomial(n, 0.11)
    stat, alarm = mon.cusum(m, n, 0.10, 0.15, h=0.0)
    assert (stat[~alarm] == 0).all()                    # memoryless: a single-week LLR rule
    a, b = mon.cusum_weights(0.10, 0.15)
    assert (alarm == (m * a + (n - m) * b > 0)).all()


def test_exact_in_control_arls_match_independent_binomial_values():
    sw = mon.nominal_arl_single_week(0.10, 0.15, 1200)
    assert sw["alarm_if_misses_at_least"] == 149 and abs(sw["llr_boundary_miss_rate"] - 0.123553) < 1e-5
    assert abs(sw["arl_weeks"] - 261.30) < 0.01
    th = mon.nominal_arl_threshold(0.90, 1200)
    assert th["low_week_if_misses_at_least"] == 181 and 2.0e15 < th["arl_weeks"] < 2.1e15


def test_threshold_arl_formula_agrees_with_simulation():
    th = mon.nominal_arl_threshold(0.90, 40, pts=5.0)     # small n so low weeks are common
    rng = np.random.default_rng(2)
    m = rng.binomial(40, 0.10, size=(4000, 400))
    first = []
    for row in m:
        al = mon.threshold_alarms(1 - row / 40, np.full(400, 400), 0.90)
        first.append(np.argmax(al) + 1 if al.any() else 401)
    assert abs(np.mean(first) - th["arl_weeks"]) / th["arl_weeks"] < 0.05


def test_threshold_arl_when_every_week_crosses():
    assert mon.nominal_arl_threshold(0.90, 1200, p_true=1.0)["arl_weeks"] == 2.0


def test_calibrate_h_refuses_a_target_beyond_the_restricted_mean():
    with pytest.raises(ValueError):
        mon.calibrate_h(0.10, 0.15, 50, 500, np.random.default_rng(0), runs=50, cap=100)
