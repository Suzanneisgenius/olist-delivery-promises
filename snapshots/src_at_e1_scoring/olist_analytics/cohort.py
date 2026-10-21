"""Weekly outcome buckets by estimated-delivery week, and a PROPOSED comparison window.

Why the window needs care
  * Activity (purchases, approvals, carrier handoffs, deliveries) drops sharply near the
    end of the file. An activity rule gives a conservative, INFERRED observation
    boundary. It is not a confirmed extraction date: a few deliveries still appear after it.
  * Late cohorts near that boundary may be right-censored or selected, so a week is
    proposed only if its end plus a lateness horizon falls before the boundary.

Two flags are kept apart on purpose:
  passes_weekly_guards  the week meets every per-week rule
  in_selected_window    the week is inside the ONE chosen consecutive window
Everything downstream (summaries, SQL, charts) uses in_selected_window.
The weekly calendar is completed first, so a missing week breaks a run.
Nothing here is frozen until the owner approves it.
"""
from __future__ import annotations

import math

import pandas as pd

from .io import ASSUMPTIONS

BUCKETS = ["A", "L", "U", "X", "NO_VALID_ESTIMATE"]


def weekly_buckets(mart: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Counts per estimated week on a complete Monday calendar.
    Returns the table and the number of orders that cannot be assigned to a week."""
    dated = mart[mart.estimated_week.notna()]
    unassigned = int(len(mart) - len(dated))
    if dated.empty:
        return pd.DataFrame(columns=["estimated_week", *BUCKETS, "orders", "eligible_orders", "otd_rate",
                                     "outcome_coverage", "confirmed_on_time_share"]), unassigned
    w = (dated.groupby(["estimated_week", "outcome_bucket"]).size().unstack(fill_value=0)
         .reindex(columns=BUCKETS, fill_value=0))
    cal = pd.date_range(w.index.min(), w.index.max(), freq="W-MON")
    w = w.reindex(cal, fill_value=0)
    w.index.name = "estimated_week"
    w["orders"] = w[BUCKETS].sum(axis=1)
    w["eligible_orders"] = w.A + w.L
    w["otd_rate"] = (w.A / w.eligible_orders).where(w.eligible_orders > 0)                 # main KPI
    conf = w.A + w.L + w.U
    w["outcome_coverage"] = (w.eligible_orders / conf).where(conf > 0)                     # guardrail
    w["confirmed_on_time_share"] = (w.A / conf).where(conf > 0)                             # auxiliary only
    return w.reset_index(), unassigned


def inferred_observation_boundary(delivered_at: pd.Series, ratio: float) -> pd.Timestamp | None:
    """Last day whose delivery count is >= ratio x the median active-day count."""
    d = delivered_at.dropna()
    if d.empty:
        return None
    daily = d.dt.normalize().value_counts().sort_index()
    daily = daily.reindex(pd.date_range(daily.index.min(), daily.index.max()), fill_value=0)
    ref = daily[daily > 0].median()
    return daily[daily >= ratio * ref].index.max()


def lateness_horizon(mart: pd.DataFrame, q: float) -> int | None:
    late = mart.loc[mart.outcome_bucket == "L", "days_late"].dropna()
    if late.empty:
        return None
    return int(math.ceil(late.quantile(q)))


def select_window(w: pd.DataFrame, boundary, horizon: int | None, min_eligible: int, min_cov: float):
    w = w.copy()
    w["week_end"] = w.estimated_week + pd.Timedelta(days=6)
    if boundary is None or horizon is None:
        w["mature"] = False
    else:
        w["mature"] = w.week_end + pd.Timedelta(days=horizon) <= boundary
    w["enough_eligible_orders"] = w.eligible_orders >= min_eligible
    w["enough_coverage"] = w.outcome_coverage.ge(min_cov)
    w["passes_weekly_guards"] = w.mature & w.enough_eligible_orders & w.enough_coverage
    runs, cur = [], []
    for i, ok in zip(w.index, w.passes_weekly_guards):
        if ok:
            cur.append(i)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    best = max(runs, key=len) if runs else []          # ties: earliest run
    w["in_selected_window"] = w.index.isin(best)
    longest = max((len(r) for r in runs), default=0)
    return w, best, longest


def summarize(w: pd.DataFrame) -> dict:
    s = w[w.in_selected_window]
    if s.empty:
        return {"status": "NO_QUALIFYING_WINDOW", "weeks": 0, "first_week": None, "last_week": None,
                "A": 0, "L": 0, "U": 0, "X": 0, "otd_rate": None, "outcome_coverage": None}
    A, L, U, X = (int(s[c].sum()) for c in ("A", "L", "U", "X"))
    return {"status": "OK", "weeks": int(len(s)),
            "first_week": str(s.estimated_week.min().date()), "last_week": str(s.estimated_week.max().date()),
            "A": A, "L": L, "U": U, "X": X,
            "otd_rate": A / (A + L) if A + L else None,
            "outcome_coverage": (A + L) / (A + L + U) if A + L + U else None,
            "confirmed_on_time_share": A / (A + L + U) if A + L + U else None}


def propose_window(w: pd.DataFrame, mart: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    p = ASSUMPTIONS["cohort_proposal"]
    boundary = inferred_observation_boundary(mart.order_delivered_customer_date, p["activity_drop_ratio"])
    horizon = lateness_horizon(mart, p["lateness_quantile"])
    w, best, longest = select_window(w, boundary, horizon, p["min_eligible_orders_per_week"], p["min_outcome_coverage"])
    summ = summarize(w)
    info = {
        "rule": (f"A+L >= {p['min_eligible_orders_per_week']} per week; outcome coverage >= {p['min_outcome_coverage']:.0%}; "
                 f"week end + horizon (ceil of p{int(p['lateness_quantile'] * 100)} of observed days late) <= inferred "
                 "observation boundary; longest consecutive run on a complete weekly calendar"),
        "last_timestamp_in_file": str(mart[["order_purchase_timestamp", "order_delivered_customer_date"]].max().max()),
        "inferred_observation_boundary": str(boundary.date()) if boundary is not None else None,
        "deliveries_after_boundary": int((mart.order_delivered_customer_date.dt.normalize() > boundary).sum())
        if boundary is not None else None,
        "lateness_horizon_days": horizon,
        "weeks_passing_guards": int(w.passes_weekly_guards.sum()),
        "longest_run_weeks": longest,
        "selected": summ,
    }
    return w, info


def sensitivity(wk: pd.DataFrame, mart: pd.DataFrame) -> pd.DataFrame:
    """Alternative windows. These are different windows, NOT confidence intervals."""
    p = ASSUMPTIONS["cohort_proposal"]
    boundary = inferred_observation_boundary(mart.order_delivered_customer_date, p["activity_drop_ratio"])
    base_h = lateness_horizon(mart, p["lateness_quantile"])
    rows = []
    for h in [base_h, *p.get("sensitivity_horizons_days", [])]:
        for cov in [p["min_outcome_coverage"], *p.get("sensitivity_coverage", [])]:
            w, _, longest = select_window(wk, boundary, h, p["min_eligible_orders_per_week"], cov)
            s = summarize(w)
            rows.append({"horizon_days": h, "min_coverage": cov, "weeks_passing_guards": int(w.passes_weekly_guards.sum()),
                         "selected_weeks": s["weeks"], "first_week": s["first_week"], "last_week": s["last_week"],
                         "otd_rate": round(s["otd_rate"], 6) if s["otd_rate"] is not None else None,
                         "is_default": h == base_h and cov == p["min_outcome_coverage"]})
    return pd.DataFrame(rows)
