"""Stage 6a: feasibility review for a survival (time-to-delivery) model. No model is fitted here.

    PYTHONPATH=src python -m olist_analytics.survival_audit

Two views are kept apart (v0.5.1):

  final-file category   what the LAST record in the file says about an order (A/L/U/X, dates).
                        Used to describe the data; it is not information available at an earlier time.
  event-date reconstructed state at a cut   rebuilt from the final file's event dates strictly BEFORE an exclusive
                        cut, assuming each event was recorded when it happened. NOT a historical system snapshot:
                          NOT_IN_RISK_SET          purchased at/after the cut
                          EVENT_RECORDED           a valid delivery record (purchase <= delivery < cut), status not X
                          RECORD_STATUS_CONFLICT   a valid delivery record before the cut, but final status canceled/unavailable
                          UNRESOLVED_AT_CUT        purchased before the cut, no valid delivery record before it
                        UNRESOLVED is not "still in transit": it mixes in-transit, later-cancelled and never-recorded orders.

Observation end: the stage-1 boundary is a DATE (2018-09-03) and stage 1 counts deliveries after that DAY.
The exclusive observation timestamp is therefore boundary + 1 day (2018-09-04 00:00); the midnight reading
(2018-09-03 00:00) is reported as a sensitivity. Neither is a confirmed extraction time.

A recent U order is only a censoring CANDIDATE: the file has no last-tracking time, so being at most N days
past the promised date is a screening rule, not proof that the order was observed until the cut.

Writes outputs/stage6a/*.csv, facts.json and feasibility_tables.md. Reads the stage-1 mart only.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from scipy import stats

from .io import ROOT, sha256

OUT = ROOT / "outputs"
S6 = OUT / "stage6a"
FINAL_CATEGORIES = ["EVENT", "RECENT_U_CANDIDATE", "U_STALE_MISSING_OUTCOME", "DELIVERED_TIME_MISSING",
                    "CANCELED_OR_UNAVAILABLE", "PURCHASED_AT_OR_AFTER_OBSERVATION_END", "NO_VALID_ESTIMATE"]
AS_OF_STATES = ["NOT_IN_RISK_SET", "EVENT_RECORDED", "RECORD_STATUS_CONFLICT", "UNRESOLVED_AT_CUT"]
DESCRIPTION = {
    "EVENT": "valid delivery record in the final file",
    "RECENT_U_CANDIDATE": "U, at most N days past promise at the observation end: censoring candidate, not confirmed",
    "U_STALE_MISSING_OUTCOME": "U, more than N days past promise: outcome missing; observation mechanism unverifiable",
    "DELIVERED_TIME_MISSING": "status delivered, no usable delivery time: event with unknown time",
    "CANCELED_OR_UNAVAILABLE": "terminal non-delivery, no cancellation time (6 also carry a delivery date: conflict)",
    "PURCHASED_AT_OR_AFTER_OBSERVATION_END": "not in the risk set at the observation end",
    "NO_VALID_ESTIMATE": "no promised date, no deadline",
}


def observation_end(boundary_date, convention: str = "day_inclusive") -> pd.Timestamp:
    """Exclusive observation timestamp. 'day_inclusive' (primary) keeps the whole boundary day."""
    b = pd.Timestamp(boundary_date).normalize()
    return b + pd.Timedelta(days=1) if convention == "day_inclusive" else b


def deadline_days(m: pd.DataFrame) -> pd.Series:
    """Late = delivered after the END of the estimated day. In days since purchase, the order is late iff
    delivery time >= deadline, so P(late) = S(deadline) for the time-to-delivery survival function S."""
    end_of_day = m.order_estimated_delivery_date.dt.normalize() + pd.Timedelta(days=1)
    return (end_of_day - m.order_purchase_timestamp).dt.total_seconds() / 86400


def valid_record_before(m: pd.DataFrame, cut) -> pd.Series:
    D, P = m.order_delivered_customer_date, m.order_purchase_timestamp
    return D.notna() & (D >= P) & (D < pd.Timestamp(cut))


def as_of(m: pd.DataFrame, cut) -> pd.DataFrame:
    """State of each order using only what was recorded before the exclusive `cut` (record-date rule)."""
    cut = pd.Timestamp(cut)
    P, D = m.order_purchase_timestamp, m.order_delivered_customer_date
    in_risk = P < cut
    rec = in_risk & valid_record_before(m, cut)
    is_x = m.outcome_bucket.eq("X")
    state = np.select([~in_risk, rec & is_x, rec], ["NOT_IN_RISK_SET", "RECORD_STATUS_CONFLICT", "EVENT_RECORDED"],
                      default="UNRESOLVED_AT_CUT")
    days = lambda a, b: (b - a).dt.total_seconds() / 86400
    out = pd.DataFrame({"as_of_state": state, "final": m.outcome_bucket}, index=m.index)
    out["duration_days"] = days(P, D).where(out.as_of_state.eq("EVENT_RECORDED"))
    out["follow_up_days"] = days(P, pd.Series(cut, index=m.index)).where(out.as_of_state.eq("UNRESOLVED_AT_CUT"))
    out["deadline_days"] = deadline_days(m)
    end_of_promised_day = m.order_estimated_delivery_date.dt.normalize() + pd.Timedelta(days=1)
    out["deadline_passed_at_cut"] = out.as_of_state.eq("UNRESOLVED_AT_CUT") & (end_of_promised_day <= cut)   # lateness already determined
    return out


def as_of_violations(m: pd.DataFrame, a: pd.DataFrame, cut) -> list[str]:
    """Guards for any survival data set built at `cut`: entry before the cut, event before the cut,
    strictly positive duration and follow-up."""
    cut = pd.Timestamp(cut)
    bad = []
    risk = a.as_of_state != "NOT_IN_RISK_SET"
    if (m.loc[risk, "order_purchase_timestamp"] >= cut).any():
        bad.append("order in risk set purchased at/after the cut")
    ev = a.as_of_state == "EVENT_RECORDED"
    if (m.loc[ev, "order_delivered_customer_date"] >= cut).any():
        bad.append("event recorded at/after the cut")
    if (a.loc[ev, "duration_days"] <= 0).any():
        bad.append("non-positive event duration")
    if (a.loc[a.as_of_state == "UNRESOLVED_AT_CUT", "follow_up_days"] <= 0).any():
        bad.append("non-positive follow-up")
    return bad


def final_category(m: pd.DataFrame, obs_end, stale_days: float) -> pd.Series:
    """Final-file description (see DESCRIPTION). Not an as-of state."""
    obs_end = pd.Timestamp(obs_end)
    b = m.outcome_bucket
    no_time = m.order_delivered_customer_date.isna() | (m.order_delivered_customer_date < m.order_purchase_timestamp)
    past_promise = (obs_end - (m.order_estimated_delivery_date.dt.normalize() + pd.Timedelta(days=1))).dt.total_seconds() / 86400
    cat = np.select(
        [b.eq("NO_VALID_ESTIMATE"), b.eq("X"), b.isin(["A", "L"]),
         m.order_purchase_timestamp >= obs_end,
         b.eq("U") & m.order_status.eq("delivered") & no_time,
         b.eq("U") & (past_promise <= stale_days),
         b.eq("U")],
        ["NO_VALID_ESTIMATE", "CANCELED_OR_UNAVAILABLE", "EVENT", "PURCHASED_AT_OR_AFTER_OBSERVATION_END",
         "DELIVERED_TIME_MISSING", "RECENT_U_CANDIDATE", "U_STALE_MISSING_OUTCOME"], default="UNCLASSIFIED")
    return pd.Series(cat, index=m.index)


def unresolved_table(universe: pd.DataFrame, cuts) -> pd.DataFrame:
    rows = []
    for T in cuts:
        a = as_of(universe, T)
        bad = as_of_violations(universe, a, T)
        if bad:
            raise AssertionError(f"as-of guards failed at {T}: {bad}")
        u = a[a.as_of_state == "UNRESOLVED_AT_CUT"]
        row = {"cutoff": str(pd.Timestamp(T).date()), "in_risk_set": int((a.as_of_state != "NOT_IN_RISK_SET").sum()),
               "event_recorded_before_T": int((a.as_of_state == "EVENT_RECORDED").sum()),
               "record_status_conflict": int((a.as_of_state == "RECORD_STATUS_CONFLICT").sum()),
               "unresolved_at_T": len(u), "deadline_passed_at_T": int(u.deadline_passed_at_cut.sum())}
        for k in ("A", "L", "U", "X"):
            row[f"later_final_{k}"] = int((u.final == k).sum())
        row["later_final_U_or_X_share"] = float(u.final.isin(["U", "X"]).mean()) if len(u) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> dict:
    from .run_stage3 import load_mart
    S6.mkdir(parents=True, exist_ok=True)
    prop = json.loads((OUT / "qa" / "stage1_facts.json").read_text())["cohort_proposal"]
    sel, horizon = prop["selected"], float(prop["lateness_horizon_days"])
    ends = {"day_inclusive (primary)": observation_end(prop["inferred_observation_boundary"], "day_inclusive"),
            "midnight (sensitivity)": observation_end(prop["inferred_observation_boundary"], "midnight")}
    obs = ends["day_inclusive (primary)"]
    m = load_mart()
    late_days = m.loc[m.outcome_bucket == "L", "days_late"]
    thresholds = {"31 (stage-1 horizon, p95 of days late)": horizon, "60 (stage-1 stale-U rule)": 60.0,
                  f"{np.ceil(late_days.quantile(0.99)):.0f} (p99 of days late)": float(np.ceil(late_days.quantile(0.99)))}
    win_mask = m.estimated_week.between(pd.Timestamp(sel["first_week"]), pd.Timestamp(sel["last_week"]))

    # 1. final-file categories: thresholds x observation-end conventions
    rows = []
    for ename, e in ends.items():
        for tname, th in thresholds.items():
            c = final_category(m, e, th)
            for k in FINAL_CATEGORIES + ["UNCLASSIFIED"]:
                rows.append({"observation_end": ename, "stale_threshold_days": tname, "category": k,
                             "orders": int((c == k).sum()), "in_window": int(((c == k) & win_mask).sum())})
    cats = pd.DataFrame(rows)

    # 2. as-of state at the observation end, against the final-file category (both conventions)
    asof_rows = []
    for ename, e in ends.items():
        a = as_of(m, e)
        bad = as_of_violations(m, a, e)
        if bad:
            raise AssertionError(f"as-of guards failed: {bad}")
        fc = final_category(m, e, horizon)
        for scope, mask in (("all orders", pd.Series(True, index=m.index)), ("approved window", win_mask)):
            t = pd.crosstab(fc[mask], a.as_of_state[mask])
            for cat_name, r in t.iterrows():
                for st, n in r.items():
                    if n:
                        asof_rows.append({"observation_end": ename, "scope": scope, "final_category": cat_name,
                                          "as_of_state": st, "orders": int(n)})
    asof_tbl = pd.DataFrame(asof_rows)
    after_cut = {ename: {"A_L_delivered_at_or_after_end": int((m.outcome_bucket.isin(["A", "L"]) & (m.order_delivered_customer_date >= e)).sum()),
                         "in_window": int((m.outcome_bucket.isin(["A", "L"]) & (m.order_delivered_customer_date >= e) & win_mask).sum()),
                         "purchased_at_or_after_end": int((m.order_purchase_timestamp >= e).sum())}
                 for ename, e in ends.items()}

    # 3. U and X detail (final file)
    u = m[m.outcome_bucket == "U"]
    past = (obs - (u.order_estimated_delivery_date.dt.normalize() + pd.Timedelta(days=1))).dt.total_seconds() / 86400
    u_summary = (pd.DataFrame({"status": u.order_status, "days_past_promise": past}).groupby("status").days_past_promise
                 .describe(percentiles=[.1, .5, .9])[["count", "10%", "50%", "90%"]].reset_index())
    x = m[m.outcome_bucket == "X"]
    x_summary = pd.DataFrame([{"status": s, "orders": int((x.order_status == s).sum()),
                               "with_carrier_date": int(x[x.order_status == s].order_delivered_carrier_date.notna().sum()),
                               "with_delivery_date": int(x[x.order_status == s].order_delivered_customer_date.notna().sum())}
                              for s in sorted(x.order_status.unique())])
    conflicts = x[x.order_delivered_customer_date.notna()][["order_id", "order_status", "order_purchase_timestamp",
                                                            "order_delivered_customer_date"]]

    # 4. unresolved orders at fold cut-offs (window, single seller), record-date rule
    universe = m[win_mask & (m.n_sellers == 1)]
    unresolved = unresolved_table(universe, ["2018-01-01", "2018-04-01", "2018-05-01", "2018-06-01"])

    # 5. distribution and follow-up support (descriptive)
    ev = m[m.outcome_bucket.isin(["A", "L"])]
    dur = (ev.order_delivered_customer_date - ev.order_purchase_timestamp).dt.total_seconds() / 86400
    lg = np.log(dur)
    q = [0.5, 0.9, 0.99, 0.999]
    dl = deadline_days(universe)
    follow = (obs - universe.order_purchase_timestamp).dt.total_seconds() / 86400
    dist = {"events_final_file": int(len(dur)), "duration_days_quantiles": {str(k): float(v) for k, v in dur.quantile(q).items()},
            "log_duration_skew": float(stats.skew(lg)), "log_duration_excess_kurtosis": float(stats.kurtosis(lg)),
            "log_duration_normal_probplot_r": float(stats.probplot(lg)[1][2]),
            "deadline_days_quantiles_universe": {str(k): float(v) for k, v in dl.quantile(q).items()},
            "universe_orders": int(len(universe)),
            "universe_min_followup_minus_deadline_days_at_primary_end": float((follow - dl).min())}

    facts = {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "mart_sha256": sha256(OUT / "marts" / "orders_mart.csv"),
             "boundary_date": prop["inferred_observation_boundary"], "observation_end_exclusive": {k: str(v) for k, v in ends.items()},
             "boundary_is_confirmed_extraction_time": False, "last_timestamp_in_file": prop["last_timestamp_in_file"],
             "after_observation_end": after_cut, "stale_thresholds_days": thresholds,
             "cancellation_timestamp_in_data": False, "last_tracking_timestamp_in_data": False,
             "u_orders": int(len(u)), "u_median_days_past_promise": float(past.median()),
             "record_status_conflicts": len(conflicts), "distribution": dist}
    cats.to_csv(S6 / "final_categories.csv", index=False)
    asof_tbl.to_csv(S6 / "final_vs_as_of_at_observation_end.csv", index=False)
    u_summary.to_csv(S6 / "u_by_status.csv", index=False)
    x_summary.to_csv(S6 / "x_by_status.csv", index=False)
    conflicts.to_csv(S6 / "record_status_conflicts.csv", index=False)
    unresolved.to_csv(S6 / "unresolved_at_cutoffs.csv", index=False)
    for stale in ("categories_by_threshold.csv", "categories_window.csv", "open_orders_at_cutoffs.csv"):   # v0.5.0 names
        (S6 / stale).unlink(missing_ok=True)
    (S6 / "facts.json").write_text(json.dumps(facts, indent=2))

    from .report import md_table
    prim = cats[cats.observation_end.str.startswith("day")].pivot(index="category", columns="stale_threshold_days", values="orders")
    prim = prim.reindex(FINAL_CATEGORIES + ["UNCLASSIFIED"])
    mid = cats[cats.observation_end.str.startswith("midnight")].pivot(index="category", columns="stale_threshold_days", values="orders")
    L = ["# Stage 6a feasibility tables (generated)", "",
         f"Boundary date {prop['inferred_observation_boundary']} (inferred, not a confirmed extraction time). "
         f"Exclusive observation end: primary {ends['day_inclusive (primary)']}, sensitivity {ends['midnight (sensitivity)']}.", "",
         "## Final-file categories, primary observation end, by stale threshold (days past promise)", "", md_table(prim.reset_index()), "",
         "## Same, midnight observation end", "", md_table(mid.reindex(FINAL_CATEGORIES + ['UNCLASSIFIED']).reset_index()), "",
         "## A/L deliveries recorded at/after each observation end", "", md_table(pd.DataFrame(after_cut).T.reset_index()), "",
         "## Final-file category vs as-of state at the observation end (31-day threshold)", "", md_table(asof_tbl), "",
         "## U orders: days past the promised date at the primary observation end, by last status", "", md_table(u_summary.round(1)), "",
         "## X orders", "", md_table(x_summary), "", "Record–status conflicts (canceled with a delivery date):", "",
         md_table(conflicts.astype(str)), "",
         "## Unresolved at fold cut-offs (window, single seller; record-date rule)", "", md_table(unresolved.round(3)), "",
         "## Distribution and follow-up (descriptive)", "", "```json", json.dumps(dist, indent=2), "```", ""]
    (S6 / "feasibility_tables.md").write_text("\n".join(L), encoding="utf-8")
    return {"cats": cats, "asof": asof_tbl, "after_cut": after_cut, "u": u_summary, "x": x_summary,
            "conflicts": conflicts, "unresolved": unresolved, "facts": facts}


if __name__ == "__main__":
    main()
    print((S6 / "feasibility_tables.md").read_text())
