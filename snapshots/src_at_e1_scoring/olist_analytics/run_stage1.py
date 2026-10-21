"""Stage 1: source manifest -> contract -> orders_mart -> quality audit -> cohort proposal.

    python -m olist_analytics.run_stage1        (from the repo root, with src/ on PYTHONPATH)
"""
from __future__ import annotations

import json
import platform
import sys

import duckdb
import pandas as pd

from .cohort import propose_window, sensitivity, weekly_buckets
from .contract import check_contract
from .gate import ReleaseBlocked, release_gate, retire_current_report, retire_stage4_outputs
from .io import CONTRACT, ROOT, load_all, raw_dir, source_manifest
from .mart import REASON_AFFECTS, build_orders_mart

OUT = ROOT / "outputs"
QA = OUT / "qa"
MARTS = OUT / "marts"


def sql_crosscheck(mart: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    con = duckdb.connect()
    q = (ROOT / "sql" / "order_outcome_buckets.sql").read_text()
    s = con.execute(q, {"orders_csv": str(raw_dir() / CONTRACT["orders"]["file"])}).df()
    s["estimated_week"] = pd.to_datetime(s.estimated_week).dt.tz_localize(None)
    p = mart.groupby(["estimated_week", "outcome_bucket"], dropna=False).size().rename("pandas_orders").reset_index()
    m = p.merge(s.rename(columns={"orders": "sql_orders"}), on=["estimated_week", "outcome_bucket"], how="outer")
    m[["pandas_orders", "sql_orders"]] = m[["pandas_orders", "sql_orders"]].fillna(0).astype(int)
    m["match"] = m.pandas_orders == m.sql_orders
    a = con.execute((ROOT / "sql" / "item_amounts.sql").read_text(),
                    {"items_csv": str(raw_dir() / CONTRACT["order_items"]["file"])}).df()
    return m, a


def manual_sample(mart: pd.DataFrame, codes: pd.DataFrame) -> pd.DataFrame:
    """~20 orders chosen to cover every rule, for a human to check against the raw files."""
    has = lambda c: mart.order_id.isin(codes.loc[codes.reason_code == c, "order_id"])
    cases = [
        ("on time", mart.outcome_bucket.eq("A") & mart.n_item_lines.eq(1), 2),
        ("late", mart.outcome_bucket.eq("L"), 2),
        ("delivered on the estimated day (on time by day rule)", mart.days_late.eq(0), 1),
        ("delivered one day after estimate", mart.days_late.eq(1), 1),
        ("in progress -> U", mart.order_status.eq("shipped"), 1),
        ("delivered but no delivery date -> U", has("delivered_missing_date"), 1),
        ("canceled with delivery date -> X", has("canceled_with_delivery_date"), 1),
        ("carrier before approval: stage invalid, OTD kept", has("carrier_before_approved") & mart.is_otd_eligible, 2),
        ("delivered before carrier handoff", has("delivered_before_carrier"), 1),
        ("same product on several lines", (mart.n_item_lines > mart.n_distinct_products), 2),
        ("multi-seller order", has("multi_seller"), 1),
        ("several payments", mart.n_payments.fillna(0) > 1, 1),
        ("payment != price + freight", has("payment_mismatch"), 1),
        ("several reviews", mart.n_reviews > 1, 1),
        ("no items", has("no_items"), 1),
        ("missing customer geo", has("missing_customer_geo"), 1),
    ]
    rows = []
    for label, mask, k in cases:
        pick = mart[mask & ~mart.order_id.isin([r["order_id"] for r in rows])]
        for r in pick.sample(min(k, len(pick)), random_state=7).itertuples():
            rows.append({"case": label, "order_id": r.order_id})
    cols = ["order_id", "order_status", "order_purchase_timestamp", "order_approved_at",
            "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date",
            "outcome_bucket", "days_late", "handling_hours", "transit_hours", "n_item_lines",
            "n_distinct_products", "n_sellers", "items_price_sum", "items_freight_sum", "payment_value_sum",
            "n_reviews", "review_score_primary", "is_otd_eligible", "is_stage_eligible",
            "is_model_eligible_prelim", "is_review_eligible", "reason_codes"]
    s = pd.DataFrame(rows).merge(mart[cols], on="order_id")
    s["reviewer_ok"] = ""          # filled in by a person after checking the raw CSVs
    s["reviewer_note"] = ""
    return s


def classify_raw_order(row: dict) -> tuple[str, int | None]:
    """Independent (stdlib-only) restatement of the bucket rule for one raw CSV row.
    Order of rules matches the mart: invalid estimate first, then X, A/L, U.
    days_late is None whenever the estimate is invalid or the delivery is not valid."""
    from datetime import datetime
    fmt = "%Y-%m-%d %H:%M:%S"
    parse = lambda v: datetime.strptime(v, fmt) if v else None
    st, pur = row["order_status"], parse(row["order_purchase_timestamp"])
    est, d = parse(row.get("order_estimated_delivery_date") or ""), parse(row.get("order_delivered_customer_date") or "")
    if est is None or (pur is not None and est.date() < pur.date()):
        return "NO_VALID_ESTIMATE", None
    if st in ("canceled", "unavailable"):
        return "X", None
    if st == "delivered" and d is not None and d >= pur:
        late = (d.date() - est.date()).days
        return ("A" if late <= 0 else "L"), late
    return "U", None


def independent_recheck(sample: pd.DataFrame) -> pd.DataFrame:
    """Re-derive bucket and days late for the sample straight from the raw CSV (csv module only)."""
    import csv
    want, got = set(sample.order_id), {}
    with open(raw_dir() / CONTRACT["orders"]["file"], newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["order_id"] in want:
                got[row["order_id"]] = classify_raw_order(row)
    s = sample.copy()
    s["recheck_bucket"] = s.order_id.map(lambda o: got[o][0])
    s["recheck_days_late"] = s.order_id.map(lambda o: got[o][1])
    s["recheck_agrees"] = (s.recheck_bucket == s.outcome_bucket) & (
        (s.recheck_days_late.fillna(-9999) == s.days_late.fillna(-9999)))
    return s


REPORT = OUT / "stage1_quality_report.md"


def main() -> dict:
    """Whole-run lifecycle: retire the current report, run, and either publish or block."""
    retire_current_report(REPORT)
    retire_current_report(OUT / "stage2_analysis.md")     # downstream results depend on this stage
    retire_current_report(OUT / "stage2" / "weekly_review_draft.html")
    retire_current_report(OUT / "stage3_model_report.md")   # stage 3 also builds on this release
    retire_stage4_outputs(OUT)                     # stage-4 pages and their UI/UAT evidence depend on this stage
    retire_current_report(OUT / "stage5_backtest_report.md")      # the backtest reuses this stage's outputs
    retire_current_report(OUT / "stage7_date_policy_report.md")   # so does the date-policy study
    retire_current_report(OUT / "stage7_monitoring_report.md")    # and its monitoring part
    try:
        return _run()
    except ReleaseBlocked:
        raise
    except BaseException as e:                              # any other failure is also a blocked release
        checks = pd.DataFrame([{"check": "run completed", "expected": "no error",
                                "actual": f"{type(e).__name__}: {e}"[:500], "pass": False}])
        release_gate(checks, REPORT, reraise=False)
        raise


def _run() -> dict:
    for d in (QA, MARTS):
        d.mkdir(parents=True, exist_ok=True)
    manifest = source_manifest()
    manifest.to_csv(QA / "source_manifest.csv", index=False)

    t = load_all()
    raw = {n: pd.read_csv(raw_dir() / s["file"], dtype=str, keep_default_na=False, na_values=[""])
           for n, s in CONTRACT.items()}
    contract = check_contract(t, raw)
    contract.to_csv(QA / "contract_results.csv", index=False)
    fails = contract[contract.status == "FAIL"]
    if len(fails):
        release_gate(pd.DataFrame({"check": "contract: " + fails.table + " / " + fails["check"],
                                   "expected": 0, "actual": fails.violations, "pass": False}), REPORT)

    mart, codes, extra = build_orders_mart(t)
    mart.to_csv(MARTS / "orders_mart.csv", index=False)
    codes.to_csv(QA / "order_reason_codes.csv", index=False)
    extra["geo_lookup"].to_csv(MARTS / "geo_lookup.csv", index=False)

    # Reconciliations
    items = t["order_items"]
    in_orders = items.order_id.isin(t["orders"].order_id)
    amount = pd.DataFrame([
        {"check": "orders_mart rows == orders rows", "expected": len(t["orders"]), "actual": len(mart)},
        {"check": "orders_mart order_id unique", "expected": 1, "actual": int(mart.order_id.is_unique)},
        {"check": "item lines carried into mart", "expected": int(in_orders.sum()), "actual": int(mart.n_item_lines.sum())},
        {"check": "price sum conserved (BRL, rounded)", "expected": round(items.loc[in_orders, "price"].sum(), 2),
         "actual": round(mart.items_price_sum.sum(), 2)},
        {"check": "freight sum conserved (BRL, rounded)", "expected": round(items.loc[in_orders, "freight_value"].sum(), 2),
         "actual": round(mart.items_freight_sum.sum(), 2)},
        {"check": "payment sum conserved (BRL, rounded)",
         "expected": round(t["order_payments"].loc[t["order_payments"].order_id.isin(mart.order_id), "payment_value"].sum(), 2),
         "actual": round(mart.payment_value_sum.sum(), 2)},
    ])
    se = mart[mart.is_stage_eligible]
    gap = (se.total_hours - se.approval_hours - se.handling_hours - se.transit_hours).abs().max()
    amount = pd.concat([amount, pd.DataFrame([
        {"check": "stage identity: total = approval + handling + transit (max abs gap, h, stage-eligible)",
         "expected": 0.0, "actual": round(float(gap), 9)}])], ignore_index=True)
    sqlw, sqla = sql_crosscheck(mart)
    amount = pd.concat([amount, pd.DataFrame([
        {"check": "SQL item lines (raw CSV)", "expected": int(sqla.item_lines[0]), "actual": int(mart.n_item_lines.sum())},
        {"check": "SQL price sum (raw CSV)", "expected": round(float(sqla.price_sum[0]), 2), "actual": round(mart.items_price_sum.sum(), 2)},
        {"check": "SQL outcome buckets: week x bucket cells matching", "expected": len(sqlw), "actual": int(sqlw.match.sum())},
    ])], ignore_index=True)
    amount["pass"] = amount.expected == amount.actual
    amount.to_csv(QA / "reconciliation_checks.csv", index=False)
    sqlw.to_csv(QA / "sql_bucket_crosscheck.csv", index=False)

    buckets = mart.outcome_bucket.value_counts().rename_axis("outcome_bucket").rename("orders").reset_index()
    buckets.to_csv(QA / "outcome_buckets.csv", index=False)
    rc = (codes.groupby(["reason_code"]).order_id.nunique().rename("orders").reset_index()
          .assign(affects=lambda d: d.reason_code.map(REASON_AFFECTS)).sort_values("orders", ascending=False))
    rc.to_csv(QA / "reason_code_counts.csv", index=False)
    elig = pd.DataFrame({k: [int(mart[k].sum())] for k in
                         ["is_otd_eligible", "is_stage_eligible", "is_model_eligible_prelim", "is_review_eligible"]}).T \
             .rename(columns={0: "orders"}).rename_axis("flag").reset_index()
    elig["share_of_all_orders"] = (elig.orders / len(mart)).round(4)
    elig.to_csv(QA / "eligibility_counts.csv", index=False)

    w, unassigned = weekly_buckets(mart)
    w, proposal = propose_window(w, mart)
    w.to_csv(QA / "weekly_buckets.csv", index=False)
    sens = sensitivity(weekly_buckets(mart)[0], mart)
    sens.to_csv(QA / "window_sensitivity.csv", index=False)

    sample = independent_recheck(manual_sample(mart, codes))
    sample.to_csv(QA / "manual_check_sample.csv", index=False)

    # Further blocking checks: week assignment, state totals, independent sample re-check.
    state_tot = mart[mart.is_otd_eligible].groupby("customer_state_reported", dropna=False).size().sum()
    amount = pd.concat([amount, pd.DataFrame([
        {"check": "weekly table orders + unassigned == mart rows", "expected": len(mart),
         "actual": int(w.orders.sum()) + unassigned},
        {"check": "OTD-eligible orders by state (incl. UNKNOWN) == all OTD-eligible", "expected": int(mart.is_otd_eligible.sum()),
         "actual": int(state_tot)},
        {"check": "independent csv-module re-check of sample (bucket, days late)", "expected": len(sample),
         "actual": int(sample.recheck_agrees.sum())},
    ])], ignore_index=True)
    amount["pass"] = amount.expected == amount.actual
    amount.to_csv(QA / "reconciliation_checks.csv", index=False)

    rv = t["order_reviews"]
    review_audit = {
        "review_rows": len(rv), "review_id_repeated_rows": int(rv.review_id.duplicated(keep=False).sum()),
        "orders_with_multiple_reviews": int((rv.groupby("order_id").size() > 1).sum()),
        "orders_with_primary_review": int(mart.is_review_eligible.sum()),
        "valid_delivered_orders_without_review_after_delivery": int(
            codes.reason_code.eq("no_review_after_delivery").sum()),
        "primary_vs_latest_score_differs": int((mart.review_score_primary.notna()
                                                & (mart.review_score_primary != mart.review_score_latest)).sum()),
    }
    otd = mart[mart.is_otd_eligible]
    stage_neg = mart.order_status.eq("delivered") & ((mart.handling_hours < 0) | (mart.transit_hours < 0))
    cba = mart[mart.order_id.isin(codes.loc[codes.reason_code == "carrier_before_approved", "order_id"])]
    recomputed = {
        "late_share_among_A_plus_L": round(float(otd.is_late.mean()), 6) if len(otd) else None,
        "A_plus_L_orders": int(len(otd)),
        "delivered_orders_with_negative_handling_or_transit": int(stage_neg.sum()),
        "definition_negative": "status delivered AND (carrier_date < approved_at OR delivered_date < carrier_date)",
        "carrier_before_approved_by_bucket": cba.outcome_bucket.value_counts().to_dict(),
    }
    sel = proposal["selected"]
    u_stale = None
    if sel["status"] == "OK" and proposal["inferred_observation_boundary"]:
        u = mart[(mart.outcome_bucket == "U") & mart.estimated_week.between(pd.Timestamp(sel["first_week"]),
                                                                              pd.Timestamp(sel["last_week"]))]
        limit = pd.Timestamp(proposal["inferred_observation_boundary"]) - pd.Timedelta(days=60)
        if len(u):
            u_stale = float(((u.order_estimated_delivery_date < limit)
                             & u.order_status.isin(["shipped", "processing", "invoiced"])).mean())
    env = {"python": sys.version.split()[0], "platform": platform.platform(), "pandas": pd.__version__,
           "numpy": __import__("numpy").__version__, "duckdb": duckdb.__version__, "pyyaml": __import__("yaml").__version__}
    facts = {"source_manifest": manifest.to_dict(orient="records"), "environment": env, "geo": extra["geo"],
             "reviews": review_audit, "recomputed_previously_quoted_numbers": recomputed,
             "cohort_proposal": proposal, "unassigned_to_week": unassigned, "u_long_unconfirmed_share": u_stale,
             "contract": contract.status.value_counts().to_dict(),
             "reconciliation_all_pass": bool(amount["pass"].all())}
    (QA / "stage1_facts.json").write_text(json.dumps(facts, indent=2, default=str), encoding="utf-8")
    r = {"mart": mart, "codes": codes, "contract": contract, "amount": amount, "weekly": w, "sens": sens,
         "facts": facts, "buckets": buckets, "rc": rc, "elig": elig, "sample": sample, "t": t}
    release_gate(amount, REPORT)
    from .report import write
    write(r, REPORT)
    return r


if __name__ == "__main__":
    r = main()
    print(r["amount"].to_string(index=False))
    print(json.dumps(r["facts"]["recomputed_previously_quoted_numbers"], indent=2))
    print(json.dumps(r["facts"]["cohort_proposal"], indent=2, default=str))
    print(r["sens"].to_string(index=False))
