"""Write outputs/stage1_quality_report.md from the stage-1 outputs (numbers only from this run)."""
from __future__ import annotations

import pandas as pd

from .io import ASSUMPTIONS, load_yaml


def readiness(selected: dict) -> tuple[str, str]:
    """Data-audit pass and comparison readiness are separate. Returns (state, explanation)."""
    if selected["status"] != "OK":
        return "NOT_READY", "No usable comparison window; weekly comparison does not proceed."
    ap = load_yaml("approvals.yaml").get("stage1", {}).get("comparison_window")
    if not ap:
        return "NEEDS_APPROVAL", "A window was computed but no owner decision is on record."
    same = (ap["first_week"], ap["last_week"], int(ap["weeks"])) == (selected["first_week"], selected["last_week"], selected["weeks"])
    if not same:
        return "NEEDS_RE_APPROVAL", (f"Computed window {selected['first_week']} → {selected['last_week']} differs from the "
                                     f"approved {ap['first_week']} → {ap['last_week']}.")
    return "READY", "Computed window matches the window on record in config/approvals.yaml."


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join("" if pd.isna(v) else str(v) for v in r.values) + " |")
    return "\n".join(lines)


def pct(x, d=2):
    return "n/a" if x is None else f"{x:.{d}%}"


def write(r: dict, path) -> None:
    f = r["facts"]
    prop = f["cohort_proposal"]
    sel = prop["selected"]
    man = pd.DataFrame(f["source_manifest"])[["table", "file", "records", "physical_lines", "columns", "sha256"]]
    man["sha256"] = man.sha256.str[:16] + "…"
    contract = r["contract"]
    soft = contract[contract.status != "PASS"][["table", "check", "violations", "rows", "policy"]]
    rec = f["recomputed_previously_quoted_numbers"]
    cba = rec["carrier_before_approved_by_bucket"]
    cba_otd = cba.get("A", 0) + cba.get("L", 0)
    sens = r["sens"].copy()
    sens["otd_rate"] = sens.otd_rate.map(lambda v: pct(v))
    env = f["environment"]
    s98 = r["sens"][(r["sens"].min_coverage == 0.98) & r["sens"].is_default.eq(False)
                    & (r["sens"].horizon_days == prop["lateness_horizon_days"])]
    L = [
        "# Stage 1 — Data Audit and Order Mart (rev. 1.1)",
        "",
        "Public Olist data, independent offline analysis. Every number below comes from this run "
        "(`python -m olist_analytics.run_stage1`) on the files fingerprinted in §1. "
        "This report is written only after every blocking check in §3 passes.",
        "",
        "## 1. Source manifest",
        f"Source: {ASSUMPTIONS['data']['source']}. Obtained: {ASSUMPTIONS['data']['obtained_via']}. "
        f"Data license: {ASSUMPTIONS['data']['data_license']}. `records` is the CSV record count; "
        "`physical_lines` differs for reviews because comments contain line breaks. Loaded source tables keep "
        "`source_record_no` (1-based record number, not a physical line number); the mart traces back by `order_id`.",
        "",
        md_table(man),
        "",
        f"Environment: Python {env['python']}, pandas {env['pandas']}, numpy {env['numpy']}, "
        f"DuckDB {env['duckdb']}, PyYAML {env['pyyaml']}.",
        "",
        "## 2. Data contract",
        f"{len(contract)} checks: " + ", ".join(f"{k} {v}" for k, v in f["contract"].items()) + ". "
        "Hard checks (keys, allowed values, zip format, parsing) pass. Foreign keys include "
        "orders.customer_id → customers.customer_id; an order without a customer record is kept and "
        "reported under state `UNKNOWN`.",
        "",
    ]
    if len(soft):
        L += ["Soft findings (handled per use, never by global deletion):", "", md_table(soft), ""]
    L += [
        "## 3. Blocking checks (release gate)",
        "Each row must pass, or the run writes `qa/RELEASE_BLOCKED.json`, deletes any previous report, "
        "and exits non-zero.",
        "",
        md_table(r["amount"]),
        "",
        "## 4. Outcome buckets (mutually exclusive, all orders)",
        "A = delivered on/before the estimated day · L = delivered after · U = outcome unconfirmed · "
        "X = canceled/unavailable · NO_VALID_ESTIMATE = estimated date missing or earlier than purchase "
        f"(never assigned to a week; {f['unassigned_to_week']} orders in this file).",
        "",
        md_table(r["buckets"]),
        "",
        "## 5. Reason codes (overlap allowed; orders per code, not additive)",
        md_table(r["rc"]),
        "",
        f"`carrier_before_approved` ({sum(cba.values()):,} orders) by bucket: "
        + ", ".join(f"{k} {v:,}" for k, v in sorted(cba.items())) + ". "
        f"Stage anomalies do not remove the {cba_otd:,} orders that already meet the OTD rule; "
        "the others are not OTD-eligible for unrelated reasons.",
        "",
        "## 6. Eligibility by use",
        md_table(r["elig"]),
        "",
        "Model eligibility is preliminary (single seller + confirmed outcome). Feature-availability rules come in stage 3.",
        "",
        "## 7. Previously quoted numbers, recomputed",
        f"- Late share among delivered orders with valid dates, L/(A+L), all weeks: **{pct(rec['late_share_among_A_plus_L'])}** "
        f"of {rec['A_plus_L_orders']:,} orders.",
        f"- Delivered orders with a negative handling or transit duration: **{rec['delivered_orders_with_negative_handling_or_transit']:,}**. "
        f"Definition: {rec['definition_negative']}. This does not cover every possible timestamp anomaly (see §5).",
        "",
        "## 8. Geolocation and reviews",
        f"- Geolocation: {f['geo']['rows']:,} points; {f['geo']['out_of_bbox_rows']} fall outside the configured "
        f"bounding box (a rectangle, not a national border) and are excluded from medians; {f['geo']['prefixes']:,} prefixes; "
        f"{f['geo']['dispersed_prefixes']} flagged as dispersed (p95 deviation > {ASSUMPTIONS['geo']['dispersion_flag_km']} km; kept).",
        f"- Reviews: {f['reviews']['review_rows']:,} records; review_id repeats on {f['reviews']['review_id_repeated_rows']:,} "
        f"records (key is review_id + order_id); {f['reviews']['orders_with_multiple_reviews']} orders have >1 review; "
        f"{f['reviews']['orders_with_primary_review']:,} orders have a primary review (first answered on/after delivery); "
        f"primary and latest score differ on {f['reviews']['primary_vs_latest_score_differs']} orders.",
        "",
        "## 9. Comparison window",
        f"- Late activity drops sharply. An activity rule gives a conservative **inferred observation boundary of "
        f"{prop['inferred_observation_boundary']}**; it is not a confirmed extraction date "
        f"({prop['deliveries_after_boundary']} deliveries still appear after it; last timestamp {prop['last_timestamp_in_file']}). "
        "Cohorts estimated near the end may be right-censored or selected, so they are left out of the main comparison.",
        f"- Horizon = {prop['lateness_horizon_days']} days: the ceiling of p95 of *observed* days late. It is itself "
        "affected by censoring and does not guarantee that 95% of unknown late orders were observed.",
        f"- Rule: {prop['rule']}.",
    ]
    if sel["status"] == "OK":
        L += [
            f"- **Selected window: estimated weeks {sel['first_week']} → {sel['last_week']} ({sel['weeks']} weeks)** — "
            f"A {sel['A']:,} · L {sel['L']:,} · U {sel['U']:,} · X {sel['X']:,}.",
            f"  - On-time rate among delivered orders with valid dates: **{pct(sel['otd_rate'])}**.",
            f"  - Outcome coverage (A+L)/(A+L+U): {pct(sel['outcome_coverage'])} — overall only; state/week levels are reported separately.",
            f"  - Auxiliary confirmed on-time share A/(A+L+U): {pct(sel.get('confirmed_on_time_share'))} — does not replace the KPI.",
        ]
    else:
        L += ["- **No usable comparison window.** No week range passes the guards; weekly comparison does not proceed."]
    L += [
        f"- Weeks passing all weekly guards: {prop['weeks_passing_guards']}; the selected window is the longest consecutive "
        f"run ({prop['longest_run_weeks']} weeks). All summaries use `in_selected_window`.",
    ]
    if f["u_long_unconfirmed_share"] is not None:
        L.append(f"- {pct(f['u_long_unconfirmed_share'], 1)} of U orders in the window have an estimated date more than "
                 "60 days before the inferred boundary and a status of shipped / processing / invoiced. They are "
                 "long-unconfirmed; the static data cannot tell why (not updated, lost, canceled without a record, or not delivered).")
    if len(s98):
        x = s98.iloc[0]
        L.append(f"- With a 98% coverage guard, {int(x.weeks_passing_guards)} weeks pass but the longest consecutive run is "
                 f"{int(x.selected_weeks)} weeks. 95% is a transparent policy choice that keeps a long comparison period; "
                 "98% is not statistically wrong.")
    L += [
        "",
        "### Window sensitivity — different windows, not confidence intervals",
        md_table(sens),
        "",
        "Differences also reflect a different mix of weeks; they are not a bias correction.",
        "",
        "## 10. Manual check",
        f"`outputs/qa/manual_check_sample.csv` lists {len(r['sample'])} orders covering the listed typical cases (boundary rules "
        "are covered by unit tests). A scripted re-check "
        "that reads the raw orders CSV with the standard `csv` module agrees on bucket and days late for "
        f"{int(r['sample'].recheck_agrees.sum())} of {len(r['sample'])}. This is a program check, not a human sign-off: "
        "`reviewer_ok` / `reviewer_note` stay empty for the person reviewing.",
        "",
    ]
    state, why = readiness(sel)
    ap = load_yaml("approvals.yaml").get("stage1", {})
    L += ["## 11. Readiness", f"- Data audit: **PASS** (every blocking check in §3 passed).",
          f"- Comparison readiness: **{state}** — {why}"]
    if state == "READY":
        L += [f"- Owner decision on record ({ap.get('decided_on')}, {ap.get('status')}); conditions:"]
        L += [f"  {i}. {c}" for i, c in enumerate(ap.get("conditions", []), 1)]
        L += ["- State decomposition (stage 2) follows `docs/metric_dictionary.md`: performance = w̄ × Δp; mix, entry "
              "and exit are measured against the common centre c = (P0+P1)/2. The overall identity holds; the mix "
              "term alone does not have a fixed total when states enter or exit."]
    L.append("")
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
