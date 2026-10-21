"""Stage 4: publish three linked local pages from the accepted stage 1–3 outputs.

    PYTHONPATH=src python -m olist_analytics.run_stage4

Pages (in outputs/): weekly_review.html · data_quality.html · model_report.html
Nothing is recomputed from raw data here: every number comes from a current, passing stage
output, and the run checks that (a) all three upstream releases are current and built on the
same mart, (b) each page's embedded data equals the export it was built from, and (c) every
local link resolves. Publishes only if all checks pass.
"""
from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve

from .dashboard import render_dashboard, weekly_frame
from .gate import ReleaseBlocked, release_gate as shared_release_gate, retire_stage4_outputs
from .io import ROOT, raw_dir, sha256
from .site import calibration_chart, hbars, line_chart, metric, nav, page, pr_curve, table

OUT = ROOT / "outputs"
S2, S3 = OUT / "stage2", OUT / "stage3"
PAGES = {"weekly": OUT / "weekly_review.html", "dq": OUT / "data_quality.html", "model": OUT / "model_report.html"}
BLOCK = OUT / "stage4" / "qa" / "RELEASE_BLOCKED.json"

pct = lambda x, d=1: "n/a" if x is None or pd.isna(x) else f"{x * 100:.{d}f}%"
num = lambda x: f"{int(x):,}"
f3 = lambda x: f"{x:.3f}"


def release_gate(checks, reraise=True):
    return shared_release_gate(checks, PAGES["model"], reraise=reraise, blocked_path=BLOCK)


def read(p, **kw):
    return pd.read_csv(p, **kw)


def records(df):
    return json.loads(df.to_json(orient="records", date_format="iso"))


# ------------------------------------------------------------------ preconditions
def preconditions() -> list[dict]:
    rows = []
    add = lambda c, ok, detail="": rows.append({"check": c, "expected": True, "actual": bool(ok), "detail": detail})
    for name, report, block in [("stage 1", OUT / "stage1_quality_report.md", OUT / "qa" / "RELEASE_BLOCKED.json"),
                                ("stage 2", OUT / "stage2_analysis.md", S2 / "qa" / "RELEASE_BLOCKED.json"),
                                ("stage 3", OUT / "stage3_model_report.md", S3 / "qa" / "RELEASE_BLOCKED.json")]:
        add(f"{name} report is current", report.exists())
        add(f"{name} is not blocked", not block.exists())
    facts = json.loads((OUT / "qa" / "stage1_facts.json").read_text())
    changed = [s["file"] for s in facts["source_manifest"] if sha256(raw_dir() / s["file"]) != s["sha256"]]
    add("raw files unchanged since stage 1", not changed, ", ".join(changed))
    l2, l3 = (json.loads((d / "lineage.json").read_text()) for d in (S2, S3))
    mart = sha256(OUT / "marts" / "orders_mart.csv")
    add("stage 2 built on the current mart", l2["mart_sha256"] == mart)
    add("stage 3 built on the current mart", l3["mart_sha256"] == mart)
    add("stage 2 built on the current stage-1 facts", l2["stage1_facts_sha256"] == sha256(OUT / "qa" / "stage1_facts.json"))
    add("stage 2 and stage 3 checks passed", bool(l2["checks_pass"]) and bool(l3["checks_pass"]))
    rows += verification_status()
    return rows


VERIFIED_METRICS = ("n", "late", "average_precision", "roc_auc", "brier", "selected", "true_late_in_selected",
                    "precision_at_top", "recall_at_top")


def bound_files() -> dict:
    """Files the independent verifier must have checked in THIS run (see scripts/verify_stage3.py)."""
    return {"test_predictions": S3 / "test_predictions.csv", "test_metrics": S3 / "test_metrics.csv",
            "stage3_checks": S3 / "stage3_checks.csv", "stage3_lineage": S3 / "lineage.json",
            "model_config": ROOT / "config" / "model.yaml", "source_manifest": OUT / "qa" / "source_manifest.csv",
            "stage1_facts": OUT / "qa" / "stage1_facts.json"}


def verification_status() -> list[dict]:
    """The independent verification must exist, say all_match, and be bound to the current stage-3 files."""
    rows = []
    add = lambda c, ok, detail="": rows.append({"check": c, "expected": True, "actual": bool(ok), "detail": detail})
    vp = S3 / "independent_verification.json"
    add("independent verification exists for this stage-3 run", vp.exists())
    if not vp.exists():
        return rows
    ver = json.loads(vp.read_text())
    add("independent verification reports all_match", ver.get("all_match") is True)
    bound = ver.get("bound_sha256", {})
    stale = [k for k, f in bound_files().items() if not f.exists() or bound.get(k) != sha256(f)]
    add("independent verification is bound to the current stage-3 files", not stale, ", ".join(stale))
    return rows


# ------------------------------------------------------------------ pages
def weekly_page() -> tuple[str, dict, bool]:
    data = json.loads((S2 / "review_data.json").read_text())
    wk = weekly_frame(data)
    faithful = render_dashboard(data, wk) == (S2 / "weekly_review_draft.html").read_text()
    return render_dashboard(data, wk, nav=nav("weekly_review.html"), base="stage2/"), data, faithful


def dq_page() -> tuple[str, dict]:
    qa = OUT / "qa"
    facts = json.loads((qa / "stage1_facts.json").read_text())
    man = read(qa / "source_manifest.csv")
    contract = read(qa / "contract_results.csv")
    recon = read(qa / "reconciliation_checks.csv")
    buckets = read(qa / "outcome_buckets.csv")
    reasons = read(qa / "reason_code_counts.csv")
    elig = read(qa / "eligibility_counts.csv")
    sens = read(qa / "window_sensitivity.csv")
    wb = read(qa / "weekly_buckets.csv", parse_dates=["estimated_week"])
    sample = read(qa / "manual_check_sample.csv")
    s2c = read(S2 / "stage2_checks.csv")
    prop, sel = facts["cohort_proposal"], facts["cohort_proposal"]["selected"]
    win = wb[wb.in_selected_window].reset_index(drop=True)
    total = int(buckets.orders.sum())
    status = contract.status.value_counts().to_dict()
    reviewed = int(sample.reviewer_ok.notna().sum())

    data = {"orders": total, "buckets": records(buckets), "contract_status": status,
            "reconciliation_pass": int(recon["pass"].astype(bool).sum()), "reconciliation_n": len(recon),
            "stage2_checks_pass": int(s2c["pass"].astype(bool).sum()), "stage2_checks_n": len(s2c),
            "window": sel, "boundary": prop["inferred_observation_boundary"],
            "deliveries_after_boundary": prop["deliveries_after_boundary"], "horizon": prop["lateness_horizon_days"],
            "sensitivity": records(sens), "sample_n": len(sample), "sample_recheck_agree": int(sample.recheck_agrees.sum()),
            "sample_reviewed": reviewed, "weekly_coverage": records(win[["estimated_week", "outcome_coverage", "U", "eligible_orders"]])}

    mv = man[["table", "file", "records", "physical_lines", "sha256"]].copy()
    mv["sha256"] = mv.sha256.str[:12] + "…"
    bv = buckets.assign(share=(buckets.orders / total).map(lambda v: pct(v, 2)), orders=buckets.orders.map(num))
    soft = contract[contract.status != "PASS"][["table", "check", "violations", "policy", "detail"]]
    sv = sens.copy()
    sv["otd_rate"] = sv.otd_rate.map(lambda v: pct(v, 2))
    ev = elig.assign(share_of_all_orders=elig.share_of_all_orders.map(lambda v: pct(v, 1)), orders=elig.orders.map(num))
    tips = [f"Week of {r.estimated_week.date()}: coverage {r.outcome_coverage:.1%}, U {int(r.U)}, eligible {int(r.eligible_orders):,}"
            for r in win.itertuples()]
    body = f"""<h1>Data Quality &amp; Exceptions</h1>
<p class="sub">Audit of the nine raw Olist tables and the one-row-per-order mart behind every page. Source hashes are fixed in the stage-1 manifest.</p>
<div class="summary">{metric("Orders in mart", num(total), "one row per order_id", "orders")}
{metric("Contract checks", f"{status.get('PASS', 0)} pass", f"{sum(v for k, v in status.items() if k != 'PASS')} soft findings, 0 hard failures", "contract")}
{metric("Blocking reconciliations", f"{data['reconciliation_pass']}/{data['reconciliation_n']}", "amounts, rows, SQL, independent sample", "recon")}
{metric("Stage-2 calculation checks", f"{data['stage2_checks_pass']}/{data['stage2_checks_n']}", "incl. 1,817 SQL state-week cells", "s2checks")}</div>
<section class="card"><h2>Every order lands in exactly one outcome bucket</h2>
<p class="muted">A on time · L late · U outcome unconfirmed · X canceled or unavailable. The main KPI uses A/(A+L); U and X are always reported beside it.</p>
{table(bv, left=("outcome_bucket",))}
<details><summary>Reason codes (an order can carry several; counts do not add up)</summary>{table(reasons, left=("reason_code", "affects"))}</details>
<details><summary>Eligibility by use</summary>{table(ev, left=("flag",))}</details></section>
<section class="card"><h2>Comparison window: {sel['first_week']} → {sel['last_week']} ({sel['weeks']} weeks)</h2>
<p>Activity drops sharply near the end of the file. An activity rule gives an <b>inferred observation boundary of {prop['inferred_observation_boundary']}</b>,
not a confirmed extraction date: {prop['deliveries_after_boundary']} deliveries still appear after it. A week enters the window only if its end plus {prop['lateness_horizon_days']} days
(p95 of observed lateness) falls before that boundary, with at least 200 eligible orders and 95% outcome coverage.</p>
{line_chart(win.estimated_week, win.outcome_coverage.tolist(), 0.95, lambda v: f"{v:.1%}", "Coverage (A+L)/(A+L+U)", tips)}
<p class="cap">Weekly outcome coverage inside the window. Hover a week for U and eligible orders.</p>
<h3>Window sensitivity — different windows, not confidence intervals</h3>{table(sv)}
<p class="notice">{pct(facts["u_long_unconfirmed_share"], 1)} of U orders in the window have an estimated date more than 60 days before the boundary and a status of shipped / processing / invoiced: long-unconfirmed. The static data cannot say why.</p></section>
<section class="card"><h2>Blocking reconciliations (stage 1)</h2>{table(recon, left=("check",), check="pass")}
<details><summary>Stage-2 calculation checks</summary>{table(s2c[["check", "expected", "actual", "pass"]], left=("check",), check="pass")}</details>
{"<details><summary>Soft contract findings (kept, handled per use)</summary>" + table(soft, left=("table", "check", "policy", "detail")) + "</details>" if len(soft) else ""}</section>
<section class="card"><h2>Source files</h2>{table(mv, left=("table", "file", "sha256"))}
<p class="cap">Reviews have more physical lines than records because comments contain line breaks.</p></section>
<section class="card"><h2>Manual check</h2>
<p data-check="sample">{len(sample)} orders covering typical cases were re-derived by an independent stdlib-only script: {data['sample_recheck_agree']} of {len(sample)} agree on bucket and days late.
Human review: <b>{reviewed} of {len(sample)}</b> marked by a reviewer. This is a program check, not a business sign-off.</p>
<div class="downloads"><a href="qa/manual_check_sample.csv" download>Sample for review</a><a href="qa/source_manifest.csv" download>Source hashes</a>
<a href="qa/reconciliation_checks.csv" download>Reconciliations</a><a href="qa/weekly_buckets.csv" download>Weekly buckets</a><a href="stage1_quality_report.md">Stage-1 report</a></div></section>"""
    return page("Data Quality & Exceptions", "data_quality.html", body, data), data


def model_page() -> tuple[str, dict]:
    res = read(S3 / "test_metrics.csv")
    tune = read(S3 / "tuning_dev.csv")
    ci = read(S3 / "test_bootstrap_ci.csv").set_index("quantity")
    cal = read(S3 / "calibration.csv")
    sens = read(S3 / "sensitivity.csv")
    seg = read(S3 / "segments.csv")
    imp = read(S3 / "permutation_importance.csv")
    splits = read(S3 / "splits.csv")
    steps = read(S3 / "population_steps.csv")
    avail = read(S3 / "label_availability.csv")
    pred = read(S3 / "test_predictions.csv")
    ver = json.loads((S3 / "independent_verification.json").read_text())
    lin = json.loads((S3 / "lineage.json").read_text())
    head = lin["headline"]
    other = "gbm" if head == "logistic" else "logistic"
    r = res.set_index("model")
    h, b, o = r.loc[head], r.loc["baseline"], r.loc[other]
    curves = {}
    for m in (head, other):
        p, rc, _ = precision_recall_curve(pred.y, pred[f"p_{m}"])
        curves[m] = (rc[::-1], p[::-1])
    mean_pred = {m: float((g.mean_predicted * g.n).sum() / g.n.sum()) for m, g in cal.groupby("model")}
    wo = sens[(sens.variant == "without estimated_days") & (sens.model == head)].iloc[0]
    ih = imp[imp.model == head].head(8)

    data = {"headline": head, "test": records(res), "ci": json.loads(ci.reset_index().to_json(orient="records")),
            "calibration_mean_predicted": mean_pred, "without_estimated_days_ap": float(wo.average_precision),
            "selection_n": ver["selection_n"], "selection_late": ver["selection_late"],
            "independent_verification_matches": ver.get("all_match") is True,
            "independent_verification_sha256": sha256(S3 / "independent_verification.json"),
            "importance_top": records(ih[["feature", "ap_drop_mean"]])}

    rv = res[["model", "n", "late", "average_precision", "roc_auc", "brier", "precision_at_top", "recall_at_top"]].copy()
    rv["average_precision"] = rv.average_precision.map(f3)
    rv["roc_auc"] = rv.roc_auc.map(f3)
    rv["brier"] = rv.brier.map(lambda v: f"{v:.4f}")
    rv["precision_at_top"] = rv.precision_at_top.map(lambda v: pct(v, 1))
    rv["recall_at_top"] = rv.recall_at_top.map(lambda v: pct(v, 1))
    tv = tune[["family", "params", "n", "late", "average_precision"]].assign(average_precision=tune.average_precision.map(f3))
    spv = splits.assign(late_rate=splits.late_rate.map(lambda v: pct(v, 1)),
                        first_purchase=splits.first_purchase.str[:10], last_purchase=splits.last_purchase.str[:10])
    av = avail.assign(late_share_excluded=avail.late_share_excluded.map(lambda v: pct(v, 1)))
    sv = sens[["variant", "model", "average_precision", "roc_auc", "precision_at_top", "recall_at_top"]].copy()
    sv["average_precision"] = sv.average_precision.map(f3)
    sv["roc_auc"] = sv.roc_auc.map(f3)
    sv["precision_at_top"] = sv.precision_at_top.map(lambda v: pct(v, 1))
    sv["recall_at_top"] = sv.recall_at_top.map(lambda v: pct(v, 1))
    gv = seg[["segment", "value", "n", "prevalence", "average_precision", "precision_at_top"]].copy()
    gv["prevalence"] = gv.prevalence.map(lambda v: pct(v, 1))
    gv["average_precision"] = gv.average_precision.map(f3)
    gv["precision_at_top"] = gv.precision_at_top.map(lambda v: pct(v, 1))
    d = ci.loc["gbm_minus_logistic"]
    body = f"""<h1>Late-Delivery Risk Model</h1>
<p class="sub">Offline simulation: score each single-seller order at checkout, rank by risk of arriving after the estimated day.
Test period {spv.first_purchase.iloc[2]} → {spv.last_purchase.iloc[2]}; model chosen on development data only.</p>
<div class="summary">{metric("Average precision (" + head + ")", f3(h.average_precision), "baseline " + f3(b.average_precision) + " = late rate", "ap")}
{metric("ROC AUC", f3(h.roc_auc), "baseline 0.500", "auc")}
{metric("Top 10% per week: precision", pct(h.precision_at_top), f"random expectation {pct(b.prevalence)}", "p10")}
{metric("Top 10% per week: late orders caught", pct(h.recall_at_top), f"{num(h.true_late_in_selected)} of {num(h.late)} late orders", "r10")}</div>
<section class="card"><h2>Ranking quality on the test period</h2>
<div class="legend"><span><i class="sw" style="background:var(--s1)"></i>{head} (headline)</span><span><i class="sw" style="background:var(--s2)"></i>{other}</span><span>dashed = random ranking</span></div>
{pr_curve(curves, float(b.prevalence))}
<p class="cap">Curves are drawn from 2% recall: precision over the first few top-ranked orders is unstable and would set the scale. AP uses the full curve.</p>
{table(rv, left=("model",))}
<p class="cap">Top 10% = per purchase week, the floor(10% × n) highest-risk orders (a hypothetical review capacity, not a real team resource).
The baseline's capacity row is one seeded random draw; its expected precision is the late rate.
{other} − {head}: ΔAP {d['p50']:+.3f} (purchase-week bootstrap 95% interval {d['p2.5']:+.3f} to {d['p97.5']:+.3f}), conditional on the fitted models and these weeks.</p></section>
<section class="card"><h2>Probabilities are too high under drift — use ranks, not risk values</h2>
<div class="two"><div>{calibration_chart(cal.assign(model=pd.Categorical(cal.model, [head, other])).sort_values(["model", "bin"]))}</div>
<div><p>Mean predicted risk: {head} {pct(mean_pred[head], 2)}, {other} {pct(mean_pred[other], 2)}; observed {pct(h.prevalence, 2)}.
Both models sit below the diagonal in every decile. The training period had a higher late rate ({pct(splits.late_rate.iloc[0])} train,
{pct(splits.late_rate.iloc[1])} dev vs {pct(splits.late_rate.iloc[2])} test). That pattern is consistent with drift; the causal reading is not tested.</p>
<p class="notice">Recalibration would need a separate calibration set whose labels are known before scoring. None is fitted here.</p></div></div></section>
<section class="card"><h2>What the score leans on</h2>
<div class="two"><div>{hbars(ih.feature.tolist(), ih.ap_drop_mean.tolist(), lambda v: f"{v:+.3f}", "AP drop when shuffled (" + head + ", test)")}</div>
<div><p>Predictive importance only; a feature here is not a cause of lateness.</p>
<p><b>Assumption to keep in view:</b> <code>estimated_days</code> treats the stored estimate as the one shown at checkout (no version history).
Without it, {head} AP falls to <b>{f3(wo.average_precision)}</b>.</p></div></div>
<details><summary>Sensitivity runs</summary>{table(sv, left=("variant", "model"))}</details>
<details><summary>Segments (scores re-ranked within each group)</summary>{table(gv, left=("segment", "value"))}</details></section>
<section class="card"><h2>Protocol: no future information</h2>
<div class="two"><div>{table(steps, left=("step",))}{table(spv, left=("split",))}</div>
<div><p>Splits follow purchase time. A label is used — for fitting <b>and</b> for choosing the model — only if the delivery happened before the cut-off.
Model choice used {ver['selection_n']:,} development orders with known labels ({ver['selection_late']:,} late).
Seller history uses only deliveries before each snapshot.</p>{table(av, left=("fit",))}
<p class="cap">Rows excluded for an unknown label are much more often late; this is the cost of not using future information.
The test period was evaluated before and after a protocol fix (v0.3.0 → v0.3.1), so it is not a fresh confirmatory test.</p></div></div>
<details><summary>Model choice on development data</summary>{table(tv, left=("family", "params"))}</details>
<p data-check="verify">Independent re-check (no project modules): population, labels and selection sample from the raw CSVs; for all three models
{len(VERIFIED_METRICS)} metrics each (n, late, AP, ROC AUC, Brier, selected, hits, precision, recall) from the saved predictions, plus the
precision/recall identities — <b>{"all match" if data["independent_verification_matches"] else "MISMATCH"}</b>.
Evidence is bound to this run's prediction, metric and config files (SHA-256 {data["independent_verification_sha256"][:12]}…).</p>
<div class="downloads"><a href="stage3_model_report.md">Model report</a><a href="stage3/test_metrics.csv" download>Test metrics</a>
<a href="stage3/test_predictions.csv" download>Test predictions</a><a href="stage3/lineage.json">Lineage</a><a href="stage3/independent_verification.json">Independent check</a></div></section>"""
    return page("Late-Delivery Risk Model", "model_report.html", body, data), data


# ------------------------------------------------------------------ checks on the pages themselves
def embedded(page_html: str, element_id: str) -> dict:
    m = re.search(rf'<script id="{element_id}" type="application/json">(.*?)</script>', page_html, re.S)
    return json.loads(m.group(1).replace("\\u003c", "<"))


def broken_links(page_html: str) -> list[str]:
    bad = []
    for t in re.findall(r'href="([^"]+)"', page_html):
        if re.match(r"^(https?:|mailto:|#|data:)", t) or t in {p.name for p in PAGES.values()}:
            continue                                   # the three pages are published together below
        if not (OUT / t).exists():
            bad.append(t)
    return bad


def page_checks(pages: dict, datas: dict, faithful: bool) -> list[dict]:
    rows = []
    add = lambda c, exp, act: rows.append({"check": c, "expected": exp, "actual": act, "detail": ""})
    add("weekly page = stage-2 page rebuilt from review_data.json (before nav/links)", True, faithful)
    add("weekly page embeds review_data.json unchanged", True,
        embedded(pages["weekly"], "review-data") == json.loads((S2 / "review_data.json").read_text()))
    wk = read(S2 / "weekly_kpis.csv")
    add("weekly page weeks == weekly_kpis.csv weeks", len(wk), len(datas["weekly"]["weekly"]))
    dq = embedded(pages["dq"], "page-data")
    b = read(OUT / "qa" / "outcome_buckets.csv")
    add("data-quality page buckets == outcome_buckets.csv", int(b.orders.sum()), int(sum(x["orders"] for x in dq["buckets"])))
    s1 = json.loads((OUT / "qa" / "stage1_facts.json").read_text())["cohort_proposal"]["selected"]
    add("data-quality page window == stage-1 selection", json.dumps(s1, sort_keys=True), json.dumps(dq["window"], sort_keys=True))
    md = embedded(pages["model"], "page-data")
    tm = read(S3 / "test_metrics.csv").set_index("model")
    shown = {x["model"]: x for x in md["test"]}
    add("model page AP / AUC / top-10% == test_metrics.csv", True,
        all(np.isclose(shown[m][k], tm.loc[m, k]) for m in tm.index
            for k in ("average_precision", "roc_auc", "precision_at_top", "recall_at_top")))
    ver = json.loads((S3 / "independent_verification.json").read_text())["score_checks"]
    diff = [f"{m}.{k}" for m in tm.index for k in VERIFIED_METRICS
            if m not in ver or not np.isclose(float(shown[m][k]), float(ver[m][k]), rtol=0, atol=1e-9)]
    add(f"model page: all {len(VERIFIED_METRICS)} metrics x {len(tm)} models == independent verification", "[]", json.dumps(diff))
    ident = [m for m in tm.index if not (np.isclose(shown[m]["precision_at_top"], shown[m]["true_late_in_selected"] / shown[m]["selected"])
                                         and np.isclose(shown[m]["recall_at_top"], shown[m]["true_late_in_selected"] / shown[m]["late"]))]
    add("model page: precision = hits/selected and recall = hits/late for every model", "[]", json.dumps(ident))
    for k, p in pages.items():
        add(f"{k} page: every local link resolves", "[]", json.dumps(broken_links(p)))
        add(f"{k} page: links to the other two pages", True, all(f'href="{n}"' in p for n in
                                                                   ("weekly_review.html", "data_quality.html", "model_report.html")))
    return rows


def main() -> dict:
    retire_stage4_outputs(OUT)
    try:
        return _run()
    except ReleaseBlocked:
        raise
    except BaseException as e:
        release_gate(pd.DataFrame([{"check": "run completed", "expected": "no error",
                                    "actual": f"{type(e).__name__}: {e}"[:500], "pass": False}]), reraise=False)
        raise


def _run() -> dict:
    pre = pd.DataFrame(preconditions())
    pre["pass"] = pre.expected.astype(str) == pre.actual.astype(str)
    release_gate(pre)
    weekly, wdata, faithful = weekly_page()
    dq, dqdata = dq_page()
    model, mdata = model_page()
    pages = {"weekly": weekly, "dq": dq, "model": model}
    chk = pd.DataFrame(page_checks(pages, {"weekly": wdata, "dq": dqdata, "model": mdata}, faithful))
    chk["pass"] = chk.expected.astype(str) == chk.actual.astype(str)
    checks = pd.concat([pre, chk], ignore_index=True)
    (OUT / "stage4").mkdir(exist_ok=True)
    checks.to_csv(OUT / "stage4" / "stage4_checks.csv", index=False)
    release_gate(checks)
    for k, p in pages.items():
        PAGES[k].write_text(p, encoding="utf-8")
    (OUT / "stage4" / "lineage.json").write_text(json.dumps({
        "pages": {k: sha256(v) for k, v in PAGES.items()},
        "inputs": {"stage2_lineage": sha256(S2 / "lineage.json"), "stage3_lineage": sha256(S3 / "lineage.json"),
                   "independent_verification": sha256(S3 / "independent_verification.json"),
                   "stage1_facts": sha256(OUT / "qa" / "stage1_facts.json"), "mart": sha256(OUT / "marts" / "orders_mart.csv")},
        "checks_pass": bool(checks["pass"].all())}, indent=2))
    return {"checks": checks}


if __name__ == "__main__":
    r = main()
    print(r["checks"][["check", "pass"]].to_string(index=False))
