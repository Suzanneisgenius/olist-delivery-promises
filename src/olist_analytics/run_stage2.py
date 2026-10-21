"""Stage 2: weekly KPIs, state decomposition, stage-timing diagnosis, independent SQL check.

    PYTHONPATH=src python -m olist_analytics.run_stage2

Runs only on a current, READY stage-1 release; publishes only if every blocking check passes.
"""
from __future__ import annotations

import json

import duckdb
import numpy as np
import pandas as pd

from .decompose import GROUP, NotComparable, decompose
from .gate import ReleaseBlocked, release_gate as shared_release_gate, retire_current_report, retire_stage4_outputs
from .io import CONTRACT, ROOT, raw_dir, sha256
from .report import readiness
from .weekly import seller_summary, stage_diagnosis, state_weekly, weekly_kpis

OUT = ROOT / "outputs"
S2 = OUT / "stage2"
REPORT = OUT / "stage2_analysis.md"
DATES = ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
         "order_delivered_customer_date", "order_estimated_delivery_date", "estimated_week", "shipping_limit_min"]


def release_gate(checks, report_path, reraise=True):
    # A stage-2 failure must not mark a previously valid stage-1 release as failed.
    return shared_release_gate(checks, report_path, reraise=reraise,
                               blocked_path=OUT / "stage2" / "qa" / "RELEASE_BLOCKED.json")


def preconditions() -> dict:
    """Stage 2 may only build on a current, passing, READY stage-1 release."""
    qa = OUT / "qa"
    problems = []
    if (qa / "RELEASE_BLOCKED.json").exists():
        problems.append("stage 1 is blocked (qa/RELEASE_BLOCKED.json present)")
    if not (OUT / "stage1_quality_report.md").exists():
        problems.append("no current stage-1 report")
    facts = json.loads((qa / "stage1_facts.json").read_text()) if (qa / "stage1_facts.json").exists() else None
    if facts is None:
        problems.append("stage-1 facts missing")
    else:
        state, why = readiness(facts["cohort_proposal"]["selected"])
        if state != "READY":
            problems.append(f"comparison readiness is {state}: {why}")
    if problems:
        release_gate(pd.DataFrame({"check": problems, "expected": "ok", "actual": "failed", "pass": False}), REPORT)
    sources = facts.get("source_manifest", [])
    changed = [s["file"] for s in sources if sha256(raw_dir() / s["file"]) != s["sha256"]]
    if changed:
        release_gate(pd.DataFrame({"check": changed, "expected": "stage-1 source hash",
                                   "actual": "changed", "pass": False}), REPORT)
    return facts


def load_mart() -> pd.DataFrame:
    m = pd.read_csv(OUT / "marts" / "orders_mart.csv", parse_dates=DATES,
                    dtype={"customer_zip_code_prefix": str, "seller_zip_code_prefix": str})
    return m


def window_weeks() -> list[pd.Timestamp]:
    w = pd.read_csv(OUT / "qa" / "weekly_buckets.csv", parse_dates=["estimated_week"])
    return sorted(w.loc[w.in_selected_window, "estimated_week"])


def sql_check(sw: pd.DataFrame, wk: pd.DataFrame, weeks) -> tuple[pd.DataFrame, pd.DataFrame]:
    con = duckdb.connect()
    q = (ROOT / "sql" / "state_week_otd.sql").read_text()
    r = con.execute(q, {"orders_csv": str(raw_dir() / CONTRACT["orders"]["file"]),
                        "customers_csv": str(raw_dir() / CONTRACT["customers"]["file"]),
                        "first_week": str(weeks[0].date()), "last_week": str(weeks[-1].date())}).df()
    r["estimated_week"] = pd.to_datetime(r.estimated_week).dt.tz_localize(None)
    st = r[r.kind == "state"].rename(columns={"state": GROUP, "a": "sql_A", "l": "sql_L"})
    st = st[(st.sql_A + st.sql_L) > 0]
    p = sw[sw.eligible_orders > 0][["estimated_week", GROUP, "A", "L"]]
    cells = p.merge(st[["estimated_week", GROUP, "sql_A", "sql_L"]], on=["estimated_week", GROUP], how="outer")
    cells = cells.fillna(0)
    cells["match"] = (cells.A == cells.sql_A) & (cells.L == cells.sql_L)
    med = wk[["estimated_week", "cycle_hours_median"]].merge(
        r[r.kind == "week"][["estimated_week", "cycle_hours_median"]].rename(columns={"cycle_hours_median": "sql_median"}),
        on="estimated_week", how="outer")
    med["abs_diff"] = (med.cycle_hours_median - med.sql_median).abs()
    return cells, med


def all_pairs(sw: pd.DataFrame, weeks) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    summaries, details = [], []
    for w0, w1 in zip(weeks[:-1], weeks[1:]):
        try:
            d, s = decompose(sw, w0, w1)
        except NotComparable as e:
            summaries.append({"prior_week": w0, "current_week": w1, "status": f"NOT_COMPARABLE: {e}"})
            continue
        ranked = d[~d.small_sample].sort_values("total")
        s.update(status="OK", top_negative_state=ranked.iloc[0][GROUP] if len(ranked) else None,
                 top_negative_total=ranked.iloc[0].total if len(ranked) else np.nan)
        summaries.append(s)
        details.append(d.assign(prior_week=w0, current_week=w1))
    return pd.DataFrame(summaries), pd.concat(details, ignore_index=True), {}


def main() -> dict:
    retire_current_report(REPORT)
    retire_current_report(S2 / "weekly_review_draft.html")
    retire_stage4_outputs(OUT)                     # stage-4 pages and their UI/UAT evidence depend on this stage
    try:
        return _run()
    except ReleaseBlocked:
        retire_current_report(S2 / "weekly_review_draft.html")
        raise
    except BaseException as e:
        retire_current_report(S2 / "weekly_review_draft.html")
        release_gate(pd.DataFrame([{"check": "run completed", "expected": "no error",
                                    "actual": f"{type(e).__name__}: {e}"[:500], "pass": False}]), REPORT, reraise=False)
        raise


def _run() -> dict:
    facts1 = preconditions()
    S2.mkdir(parents=True, exist_ok=True)
    m = load_mart()
    weeks = window_weeks()
    sel = facts1["cohort_proposal"]["selected"]

    wk = weekly_kpis(m, weeks)
    sw = state_weekly(m, weeks)
    dist, lim = stage_diagnosis(m, weeks)
    sellers = seller_summary(m, weeks)
    pairs, detail, _ = all_pairs(sw, weeks)
    latest_d, latest_s = decompose(sw, weeks[-2], weeks[-1])
    ok_pairs = pairs[pairs.status == "OK"].copy()
    big = ok_pairs.loc[ok_pairs.change.abs().idxmax()]
    big_d, big_s = decompose(sw, big.prior_week, big.current_week)
    cells, med = sql_check(sw, wk, weeks)
    with duckdb.connect() as con:
        sql_dist = con.execute((ROOT / "sql" / "stage_timing.sql").read_text(),
                              {"orders_csv": str(raw_dir()/CONTRACT["orders"]["file"]),
                               "first_week": str(weeks[0].date()), "last_week": str(weeks[-1].date())}).df()
    stage_cross = dist.merge(sql_dist, on=["group", "stage"], how="outer", suffixes=("", "_sql"))
    stage_cross["match"] = stage_cross.n.eq(stage_cross.n_sql)
    for c in ["median_h", "p90_h", "mean_h"]:
        stage_cross["match"] &= np.isclose(stage_cross[c], stage_cross[c+"_sql"], rtol=0, atol=1e-6)

    tot = sw.groupby("estimated_week").eligible_orders.sum().reindex(weeks).fillna(0).astype(int)
    checks = pd.DataFrame([
        {"check": "window weeks used == approved selection", "expected": f"{sel['first_week']}..{sel['last_week']} ({sel['weeks']})",
         "actual": f"{weeks[0].date()}..{weeks[-1].date()} ({len(weeks)})"},
        {"check": "window A / L / U / X == stage-1 selection", "expected": f"{sel['A']}/{sel['L']}/{sel['U']}/{sel['X']}",
         "actual": f"{wk.A.sum()}/{wk.L.sum()}/{wk.U.sum()}/{wk.X.sum()}"},
        {"check": "state eligible totals == weekly eligible (every week)", "expected": len(weeks),
         "actual": int((tot.values == wk.set_index('estimated_week').eligible_orders.reindex(weeks).values).sum())},
        {"check": "decomposition identity holds for every comparable pair (max |gap| < 1e-12)", "expected": True,
         "actual": bool(ok_pairs.identity_gap.abs().max() < 1e-12)},
        {"check": "SQL state x week A/L cells matching", "expected": len(cells), "actual": int(cells.match.sum())},
        {"check": "SQL weekly median cycle hours (max |diff| < 1e-6 h)", "expected": True,
         "actual": bool(med.abs_diff.max() < 1e-6)},
        {"check": "SQL stage timing n, median, P90 and mean (all outcome-stage cells)",
         "expected": len(stage_cross), "actual": int(stage_cross.match.sum())},
    ])
    checks["pass"] = checks.expected.astype(str) == checks.actual.astype(str)

    wk.to_csv(S2 / "weekly_kpis.csv", index=False)
    sw.to_csv(S2 / "state_weekly.csv", index=False)
    pairs.to_csv(S2 / "decomposition_pairs.csv", index=False)
    detail.to_csv(S2 / "decomposition_by_state_all_pairs.csv", index=False)
    latest_d.to_csv(S2 / "figure04a_latest_pair.csv", index=False)
    big_d.to_csv(S2 / "decomposition_largest_change_pair.csv", index=False)
    dist.to_csv(S2 / "stage_timing_by_outcome.csv", index=False)
    lim.to_csv(S2 / "seller_handoff_vs_shipping_limit.csv", index=False)
    sellers.to_csv(S2 / "seller_review_queue.csv", index=False)
    cells.to_csv(S2 / "sql_state_week_crosscheck.csv", index=False)
    med.to_csv(S2 / "sql_weekly_median_crosscheck.csv", index=False)
    stage_cross.to_csv(S2 / "sql_stage_timing_crosscheck.csv", index=False)
    checks.to_csv(S2 / "stage2_checks.csv", index=False)

    r = {"m": m, "weeks": weeks, "sel": sel, "wk": wk, "sw": sw, "dist": dist, "lim": lim, "pairs": pairs,
         "latest": (latest_d, latest_s), "big": (big_d, big_s), "checks": checks, "facts1": facts1,
         "detail": detail, "sellers": sellers}
    release_gate(checks, REPORT)
    from .report2 import write
    write(r, REPORT, S2)
    from .dashboard import write_dashboard
    write_dashboard(r, S2 / "weekly_review_draft.html")
    lineage = {"source_manifest": facts1["source_manifest"],
               "mart_sha256": sha256(OUT/"marts/orders_mart.csv"),
               "stage1_facts_sha256": sha256(OUT/"qa/stage1_facts.json"),
               "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
               "comparison_window": sel, "checks_pass": bool(checks["pass"].all())}
    (S2/"lineage.json").write_text(json.dumps(lineage, indent=2))
    return r


if __name__ == "__main__":
    r = main()
    print(r["checks"].to_string(index=False))
