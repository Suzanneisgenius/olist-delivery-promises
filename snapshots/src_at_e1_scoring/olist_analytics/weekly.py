"""Weekly KPIs, state-week table and stage-timing diagnosis inside the approved window."""
from __future__ import annotations

import pandas as pd

GROUP = "customer_state_reported"
STAGES = ["approval_hours", "handling_hours", "transit_hours", "total_hours"]


def q(x: pd.Series, p: float):
    x = x.dropna()
    return float(x.quantile(p)) if len(x) else float("nan")


def weekly_kpis(m: pd.DataFrame, weeks: list[pd.Timestamp]) -> pd.DataFrame:
    """One row per window week. OTD and guardrails, cycle and stage hours with their own n."""
    rows = []
    for wk in weeks:
        g = m[m.estimated_week == wk]
        A, L, U, X = (int((g.outcome_bucket == b).sum()) for b in "ALUX")
        ae = g[g.is_otd_eligible]
        st = g[g.is_stage_eligible & g.is_otd_eligible]
        row = {"estimated_week": wk, "orders": len(g), "A": A, "L": L, "U": U, "X": X,
               "eligible_orders": A + L,
               "otd_rate": A / (A + L) if A + L else float("nan"),
               "outcome_coverage": (A + L) / (A + L + U) if A + L + U else float("nan"),
               "confirmed_on_time_share": A / (A + L + U) if A + L + U else float("nan"),
               "cycle_hours_median": q(ae.total_hours, .5), "cycle_hours_p90": q(ae.total_hours, .9),
               "cycle_hours_n": int(ae.total_hours.notna().sum()),
               "stage_eligible_n": len(st)}
        for s in ("handling_hours", "transit_hours"):
            row[f"{s}_median"], row[f"{s}_p90"] = q(st[s], .5), q(st[s], .9)
        rows.append(row)
    return pd.DataFrame(rows)


def state_weekly(m: pd.DataFrame, weeks: list[pd.Timestamp]) -> pd.DataFrame:
    g = m[m.estimated_week.isin(weeks)]
    t = (g.groupby(["estimated_week", GROUP]).outcome_bucket.value_counts().unstack(fill_value=0)
         .reindex(columns=["A", "L", "U", "X", "NO_VALID_ESTIMATE"], fill_value=0).reset_index())
    t["eligible_orders"] = t.A + t.L
    t["otd_rate"] = (t.A / t.eligible_orders).where(t.eligible_orders > 0)
    conf = t.A + t.L + t.U
    t["outcome_coverage"] = (t.eligible_orders / conf).where(conf > 0)
    return t


def stage_diagnosis(m: pd.DataFrame, weeks: list[pd.Timestamp]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stage-hour distributions for on-time vs late orders (stage-eligible only), and the share of
    orders handed to the carrier after the seller's shipping_limit_date. Descriptive, not blame."""
    g = m[m.estimated_week.isin(weeks) & m.is_stage_eligible & m.is_otd_eligible].copy()
    g["group"] = g.outcome_bucket.map({"A": "on time (A)", "L": "late (L)"})
    rows = []
    for name, x in g.groupby("group"):
        for s in STAGES:
            rows.append({"group": name, "stage": s.replace("_hours", ""), "n": int(x[s].notna().sum()),
                         "median_h": q(x[s], .5), "p90_h": q(x[s], .9), "mean_h": float(x[s].mean())})
    dist = pd.DataFrame(rows)
    g["handoff_after_limit"] = g.order_delivered_carrier_date > g.shipping_limit_min
    g["has_limit"] = g.shipping_limit_min.notna()
    lim = (g[g.has_limit].groupby("group")
           .agg(orders=("order_id", "size"), handoff_after_limit=("handoff_after_limit", "sum")).reset_index())
    lim["share_after_limit"] = lim.handoff_after_limit / lim.orders
    return dist, lim


def seller_summary(m: pd.DataFrame, weeks, min_n: int = 30) -> pd.DataFrame:
    """Single-seller orders only. Describe seller-associated outcomes without assigning blame.

    Wilson intervals summarize binomial sampling uncertainty only, not confounding or censoring.
    """
    g = m[m.estimated_week.isin(weeks) & m.single_seller_id.notna()].copy()
    rows = []
    for seller, x in g.groupby("single_seller_id"):
        a, l, u, canceled = [int(x.outcome_bucket.eq(b).sum()) for b in "ALUX"]
        n = a + l
        if not n:
            continue
        p, z = a / n, 1.959963984540054
        center = (p + z*z/(2*n)) / (1 + z*z/n)
        half = z * (p*(1-p)/n + z*z/(4*n*n))**.5 / (1 + z*z/n)
        st = x[x.is_otd_eligible & x.is_stage_eligible]
        rows.append({"single_seller_id": seller, "seller_state": x.seller_state.iloc[0],
                     "A": a, "L": l, "U": u, "X": canceled, "eligible_orders": n,
                     "otd_rate": p, "outcome_coverage": n/(n+u),
                     "otd_wilson_low": center-half, "otd_wilson_high": center+half,
                     "stage_n": len(st), "handling_median_h": q(st.handling_hours, .5),
                     "transit_median_h": q(st.transit_hours, .5), "meets_min_n": n >= min_n})
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    # Stable aliases keep identifiers out of the reader-facing dashboard.
    aliases = {s: f"Seller {i+1:04d}" for i, s in enumerate(sorted(result.single_seller_id))}
    result["seller_label"] = result.single_seller_id.map(aliases)
    return result.sort_values(["otd_rate", "eligible_orders", "single_seller_id"],
                              ascending=[True, False, True]).reset_index(drop=True)
