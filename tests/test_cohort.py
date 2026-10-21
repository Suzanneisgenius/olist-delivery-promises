"""Window selection: guards vs selected window, calendar gaps, and empty/edge inputs."""
import pandas as pd
import pytest

from olist_analytics.cohort import (lateness_horizon, select_window, summarize, weekly_buckets,
                                    inferred_observation_boundary)

W = pd.Timestamp


def wk(rows):
    """rows: (week, A, L, U) -> weekly table as produced by weekly_buckets."""
    recs = []
    for week, a, l, u in rows:
        recs += [{"estimated_week": W(week), "outcome_bucket": b} for b, n in (("A", a), ("L", l), ("U", u)) for _ in range(n)]
    mart = pd.DataFrame(recs)
    return weekly_buckets(mart)


def test_missing_week_breaks_the_run_and_flags_stay_separate():
    # three good weeks, one ABSENT week (2018-01-22), then four good weeks
    rows = [(d, 300, 10, 0) for d in ["2018-01-01", "2018-01-08", "2018-01-15",
                                      "2018-01-29", "2018-02-05", "2018-02-12", "2018-02-19"]]
    w, unassigned = wk(rows)
    assert W("2018-01-22") in set(w.estimated_week)            # calendar completed
    w, best, longest = select_window(w, boundary=W("2018-12-31"), horizon=30, min_eligible=200, min_cov=0.95)
    assert w.passes_weekly_guards.sum() == 7
    assert w.in_selected_window.sum() == 4 and longest == 4    # only the longest consecutive run
    s = summarize(w)
    assert (s["first_week"], s["last_week"], s["weeks"]) == ("2018-01-29", "2018-02-19", 4)
    assert s["A"] == 1200                                      # summary uses the selected window only


def test_min_eligible_uses_a_plus_l_not_all_orders():
    w, _ = wk([("2018-01-01", 150, 10, 100)])                  # 260 orders but only 160 eligible
    w, *_ = select_window(w, W("2018-12-31"), 30, min_eligible=200, min_cov=0.0)
    assert not w.passes_weekly_guards.any()


def test_zero_denominator_is_missing_not_zero():
    w, _ = wk([("2018-01-01", 0, 0, 5)])
    assert pd.isna(w.otd_rate.iloc[0]) and w.outcome_coverage.iloc[0] == 0


def test_no_late_orders_gives_no_horizon_and_no_window():
    mart = pd.DataFrame({"outcome_bucket": ["A", "A"], "days_late": [-2.0, 0.0]})
    assert lateness_horizon(mart, 0.95) is None
    w, _ = wk([("2018-01-01", 300, 0, 0)])
    w, best, longest = select_window(w, W("2018-12-31"), None, 200, 0.95)
    assert best == [] and summarize(w)["status"] == "NO_QUALIFYING_WINDOW"


def test_empty_inputs_do_not_crash():
    w, unassigned = weekly_buckets(pd.DataFrame({"estimated_week": pd.Series([pd.NaT]), "outcome_bucket": ["NO_VALID_ESTIMATE"]}))
    assert w.empty and unassigned == 1
    assert inferred_observation_boundary(pd.Series([pd.NaT]), 0.1) is None


def test_boundary_ignores_thin_tail():
    days = pd.to_datetime(["2018-01-01"] * 100 + ["2018-01-02"] * 100 + ["2018-01-05"] * 2)
    assert inferred_observation_boundary(pd.Series(days), 0.10) == W("2018-01-02")
