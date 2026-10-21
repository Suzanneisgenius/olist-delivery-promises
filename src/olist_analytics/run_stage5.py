"""Stage 5: monthly rolling-origin backtest of the stage-3 models (retrospective stability study).

    PYTHONPATH=src python -m olist_analytics.run_stage5

For each cut-off T in config/backtest.yaml (2018-04-01, 2018-05-01, 2018-06-01):
  fit rows   : population orders purchased before T whose delivery (the label) happened before T;
  eval rows  : population orders purchased in [T, T + 1 month);
  seller history for fit rows uses month-start snapshots, for eval rows a snapshot frozen at T;
  logistic and GBM use the stage-3 hyperparameters (no tuning per fold); baseline = fit late rate.
Reports per fold: late share, AP, ROC AUC, Brier, weekly top-10% hits, and how many training labels were
still unknown at T. All evaluation months lie in the stage-3 test period that was already inspected,
so this is a stability study, not a new test. Published only if every blocking check passes.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .features import FEATURES, CFG, attach_seller, check_whitelist, model_population, month_start, order_features
from .gate import ReleaseBlocked, release_gate as shared_release_gate, retire_current_report
from .io import ROOT, load_yaml, raw_dir, sha256
from .modeling import gbm, logistic, score_metrics, top_share_by_week

OUT = ROOT / "outputs"
S3, S5 = OUT / "stage3", OUT / "stage5"
REPORT = OUT / "stage5_backtest_report.md"
BT = load_yaml("backtest.yaml")


def release_gate(checks, reraise=True):
    return shared_release_gate(checks, REPORT, reraise=reraise, blocked_path=S5 / "qa" / "RELEASE_BLOCKED.json")


def preconditions() -> list[dict]:
    from .run_stage4 import verification_status
    rows = []
    add = lambda c, ok, detail="": rows.append({"check": c, "expected": True, "actual": bool(ok), "detail": detail})
    add("stage 3 report is current", (OUT / "stage3_model_report.md").exists())
    add("stage 3 is not blocked", not (S3 / "qa" / "RELEASE_BLOCKED.json").exists())
    facts = json.loads((OUT / "qa" / "stage1_facts.json").read_text())
    changed = [s["file"] for s in facts["source_manifest"] if sha256(raw_dir() / s["file"]) != s["sha256"]]
    add("raw files unchanged since stage 1", not changed, ", ".join(changed))
    l3 = json.loads((S3 / "lineage.json").read_text())
    add("stage 3 built on the current mart", l3["mart_sha256"] == sha256(OUT / "marts" / "orders_mart.csv"))
    rows += verification_status()
    return rows


def fold_split(pop: pd.DataFrame, T, E) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """fit = purchased before T AND label known before T; eval = purchased in [T, E);
    pending = purchased before T but delivered at/after T (label unknown at T, excluded from the fit)."""
    T, E = pd.Timestamp(T), pd.Timestamp(E)
    before = pop.order_purchase_timestamp < T
    known = pop.order_delivered_customer_date < T
    fit = pop[before & known]
    pending = pop[before & ~known]
    ev = pop[(pop.order_purchase_timestamp >= T) & (pop.order_purchase_timestamp < E)]
    return fit, ev, pending


def fold_checks(fold: str, fit, ev, T, E, metas_fit, metas_ev) -> list[dict]:
    T, E = pd.Timestamp(T), pd.Timestamp(E)
    snap_ok = all(m["max_label_delivery"] is None or pd.Timestamp(m["max_label_delivery"]) < pd.Timestamp(m["T"])
                  for m in metas_fit + metas_ev)
    rows = [
        (f"{fold}: fit uses only labels delivered before T", True, bool((fit.order_delivered_customer_date < T).all())),
        (f"{fold}: fit uses only purchases before T", True, bool((fit.order_purchase_timestamp < T).all())),
        (f"{fold}: eval purchases inside [T, T+1 month)", True,
         bool(((ev.order_purchase_timestamp >= T) & (ev.order_purchase_timestamp < E)).all())),
        (f"{fold}: no eval order in the fit", 0, len(set(ev.order_id) & set(fit.order_id))),
        (f"{fold}: eval seller snapshot frozen at T", [str(T)], sorted({m["T"] for m in metas_ev})),
        (f"{fold}: every seller snapshot holds only labels delivered before its T", True, snap_ok),
        (f"{fold}: eval block has both classes", True, bool(0 < ev.is_late.sum() < len(ev))),
    ]
    return [{"check": c, "expected": e, "actual": a} for c, e, a in rows]


def reproduces_stage3(fold_pred: pd.DataFrame, stage3_pred: pd.DataFrame, tol: float = 1e-9) -> tuple[bool, str]:
    """Same rows, same fit data and same frozen snapshot as stage 3 → identical scores for April purchases."""
    m = fold_pred.merge(stage3_pred, on="order_id", suffixes=("", "_s3"))
    if len(m) != len(fold_pred) or m.empty:
        return False, f"{len(m)} of {len(fold_pred)} rows found in stage-3 predictions"
    d = max(float(np.max(np.abs(m[f"p_{k}"] - m[f"p_{k}_s3"]))) for k in ("logistic", "gbm"))
    return d <= tol, f"max |difference| = {d:.2e} over {len(m):,} orders"


def population_steps(mart: pd.DataFrame, sel: dict, T, E) -> dict:
    """How the evaluation month shrinks from all purchases to the modelled population."""
    T, E = pd.Timestamp(T), pd.Timestamp(E)
    m = mart[(mart.order_purchase_timestamp >= T) & (mart.order_purchase_timestamp < E)]
    w = m[m.estimated_week.between(pd.Timestamp(sel["first_week"]), pd.Timestamp(sel["last_week"]))]
    al = w[w.outcome_bucket.isin(["A", "L"])]
    one = al[al.n_sellers == 1]
    est = lambda d: float((d.order_estimated_delivery_date.dt.normalize() - d.order_purchase_timestamp.dt.normalize()).dt.days.median())
    return {"purchased_in_month": len(m), "estimated_week_in_window": len(w), "final_A_or_L": len(al),
            "single_seller": len(one), "outside_window": len(m) - len(w),
            "U_or_X_inside_window": int(w.outcome_bucket.isin(["U", "X"]).sum()),
            "median_estimated_days_all_purchases": est(m), "median_estimated_days_modelled": est(one)}


def main() -> dict:
    retire_current_report(REPORT)
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
    for d in (S5, S5 / "qa"):
        d.mkdir(parents=True, exist_ok=True)

    from .run_stage3 import load_mart, purchase_week
    facts = json.loads((OUT / "qa" / "stage1_facts.json").read_text())
    sel = facts["cohort_proposal"]["selected"]
    l3 = json.loads((S3 / "lineage.json").read_text())
    params = l3["parameters"]
    k, share, seed = CFG["seller_history"]["smoothing_k"], BT["evaluation"]["top_share"], CFG["models"]["seed"]

    mart = load_mart()
    history = mart[(mart.n_sellers == 1) & mart.single_seller_id.notna()]
    pop, _ = model_population(mart, sel["first_week"], sel["last_week"])
    pop["pweek"] = purchase_week(pop.order_purchase_timestamp)
    base = order_features(pop)
    y_all = pop.is_late.astype(int)

    metrics, avail, popn, preds, snaps, checks = [], [], [], [], [], []
    for T in BT["cutoffs"]:
        T = pd.Timestamp(T)
        E = T + pd.DateOffset(months=BT["block_months"])
        fold = str(T.date())
        fit, ev, pending = fold_split(pop, T, E)
        X_fit, m_fit = attach_seller(fit, base.loc[fit.index], history, month_start(fit.order_purchase_timestamp), k)
        X_ev, m_ev = attach_seller(ev, base.loc[ev.index], history, pd.Series(T, index=ev.index), k)
        X_fit, X_ev = X_fit[FEATURES], X_ev[FEATURES]
        check_whitelist(X_fit), check_whitelist(X_ev)
        ytr, yev = y_all[fit.index], y_all[ev.index]
        week = ev.pweek
        scores = {"baseline": np.full(len(ev), float(ytr.mean())),
                  "logistic": logistic(params["logistic"]["C"]).fit(X_fit, ytr).predict_proba(X_ev)[:, 1],
                  "gbm": gbm(params["gbm"]).fit(X_fit, ytr).predict_proba(X_ev)[:, 1]}
        for name, s in scores.items():
            row = {"cutoff": fold, "eval_from": fold, "eval_to": str(E.date()), "model": name,
                   **score_metrics(yev, s, week, share), "mean_predicted": float(np.mean(s))}
            if name == "baseline":                # constant score: seeded random capacity draw, as in stage 3
                order = np.random.default_rng(seed).permutation(len(ev))
                row.update(top_share_by_week(np.asarray(yev)[order], s[order], np.asarray(week)[order], share))
            metrics.append(row)
        avail.append({"cutoff": fold, "fit_rows": len(fit), "fit_late_rate": float(ytr.mean()),
                      "pending_at_T": len(pending), "pending_late_rate": float(y_all[pending.index].mean()) if len(pending) else np.nan,
                      "pending_last_delivery": str(pending.order_delivered_customer_date.max()) if len(pending) else None})
        popn.append({"cutoff": fold, **population_steps(mart, sel, T, E), "eval_rows": len(ev)})
        preds.append(pd.DataFrame({"cutoff": fold, "order_id": ev.order_id.values, "purchase_week": week.dt.date.values,
                                   "y": yev.values, **{f"p_{n}": s for n, s in scores.items()}}))
        snaps += [dict(cutoff=fold, use=u, **x) for u, ms in (("fit", m_fit), ("eval frozen", m_ev)) for x in ms]
        checks += fold_checks(fold, fit, ev, T, E, m_fit, m_ev)

    metrics, preds = pd.DataFrame(metrics), pd.concat(preds, ignore_index=True)
    s3_pred = pd.read_csv(S3 / "test_predictions.csv")
    first = preds[preds.cutoff == BT["cutoffs"][0]]
    ok, detail = reproduces_stage3(first[["order_id", "p_logistic", "p_gbm"]], s3_pred)
    checks.append({"check": f"fold {BT['cutoffs'][0]} reproduces stage-3 test scores for its month", "expected": True,
                   "actual": ok, "detail": detail})
    checks.append({"check": "evaluation months are inside the stage-3 test period (stability study, not a new test)",
                   "expected": True, "actual": bool(set(preds.order_id) <= set(s3_pred.order_id))})
    checks = pd.DataFrame(checks)
    checks["pass"] = checks.expected.astype(str) == checks.actual.astype(str)
    allchk = pd.concat([pre, checks], ignore_index=True)

    metrics.to_csv(S5 / "fold_metrics.csv", index=False)
    pd.DataFrame(avail).to_csv(S5 / "fold_label_availability.csv", index=False)
    pd.DataFrame(popn).to_csv(S5 / "fold_population.csv", index=False)
    preds.to_csv(S5 / "fold_predictions.csv", index=False)
    pd.DataFrame(snaps).to_csv(S5 / "seller_snapshots.csv", index=False)
    allchk.to_csv(S5 / "stage5_checks.csv", index=False)
    (S5 / "lineage.json").write_text(json.dumps({
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "cutoffs": BT["cutoffs"],
        "parameters_from_stage3": params, "stage3_lineage_sha256": sha256(S3 / "lineage.json"),
        "mart_sha256": sha256(OUT / "marts" / "orders_mart.csv"), "config_sha256": sha256(ROOT / "config" / "backtest.yaml"),
        "environment": {"pandas": pd.__version__, "numpy": np.__version__, "sklearn": __import__("sklearn").__version__},
        "checks_pass": bool(allchk["pass"].all())}, indent=2))
    release_gate(allchk)
    segments = preds.groupby("cutoff").purchase_week.nunique()
    r = {"metrics": metrics, "avail": pd.DataFrame(avail), "popn": pd.DataFrame(popn), "checks": allchk, "segments": segments,
         "params": params, "headline": l3["headline"]}
    write_report(r)
    return r


# ------------------------------------------------------------------ report (numbers only from this run)
def write_report(r: dict) -> None:
    from .report import md_table
    pct = lambda x, d=1: "n/a" if pd.isna(x) else f"{x * 100:.{d}f}%"
    f3 = lambda x: f"{x:.3f}"
    m = r["metrics"]
    t = m[["cutoff", "model", "n", "late", "prevalence", "mean_predicted", "average_precision", "roc_auc", "brier",
           "selected", "true_late_in_selected", "precision_at_top", "recall_at_top"]].copy()
    for c in ("prevalence", "mean_predicted", "precision_at_top", "recall_at_top"):
        t[c] = t[c].map(pct)
    for c in ("average_precision", "roc_auc"):
        t[c] = t[c].map(f3)
    t["brier"] = t.brier.map(lambda v: f"{v:.4f}")
    w = m.pivot(index="cutoff", columns="model", values="average_precision")
    lift = (w["logistic"] / w["baseline"]).round(2)
    best = w[["logistic", "gbm"]].idxmax(axis=1)
    bs = m.pivot(index="cutoff", columns="model", values="brier")
    auc = m.pivot(index="cutoff", columns="model", values="roc_auc")
    mp = m.pivot(index="cutoff", columns="model", values="mean_predicted")
    prev = m.pivot(index="cutoff", columns="model", values="prevalence")["logistic"]
    lr_below = int((bs.logistic < bs.baseline).sum())
    a = r["avail"].copy()
    a["fit_late_rate"] = a.fit_late_rate.map(pct)
    a["pending_late_rate"] = a.pending_late_rate.map(pct)
    p = r["popn"]
    cut = ", ".join(f"{x.cutoff} {x.outside_window:,} of {x.purchased_in_month:,} ({x.outside_window / x.purchased_in_month:.1%})"
                    for x in p.itertuples())
    med = ", ".join(f"{x.cutoff} {x.median_estimated_days_all_purchases:.0f} → {x.median_estimated_days_modelled:.0f}"
                    for x in p.itertuples())
    L = ["# Stage 5 — Monthly Rolling-Origin Backtest", "",
         "> **Retrospective stability study, not a new test.** All three evaluation months lie inside the stage-3 test period, "
         "which was inspected in v0.3.0 and v0.3.1. Hyperparameters are the frozen stage-3 choice (selected with labels known "
         "before 2018-04-01); nothing is tuned per fold.", "",
         "## Protocol", "",
         "- Cut-offs T: " + ", ".join(BT["cutoffs"]) + ". Fit on population orders purchased before T **whose delivery happened before T**; "
         "evaluate purchases in [T, T + 1 month).",
         "- Seller history: fit rows use month-start snapshots; evaluation rows use one snapshot frozen at T (no labels from inside the month).",
         f"- Models: baseline (fit late rate), logistic C={r['params']['logistic']['C']}, GBM {json.dumps(r['params']['gbm'])}.",
         "- Top 10%: per purchase week inside the month, floor(10% × n) highest scores; weeks crossing a month edge are split.",
         f"- The 2018-04-01 fold uses the same fit rows and snapshot as stage 3, and reproduces its April scores ({r['checks'][r['checks'].check.str.contains('reproduces')].detail.iloc[0]}).", "",
         "## Results by fold", "", md_table(t), "",
         "## Reading", "",
         "**Summary.** In each of the three selected monthly cohorts the models keep a ranking signal above the constant "
         "reference; over-prediction of probabilities persists in every fold; **temporal stability is not established** "
         "(three points, changing cohorts, no intervals).", "",
         "- AP relative to the constant reference (= late share of the month), logistic: " + ", ".join(f"{c} ×{v}" for c, v in lift.items())
         + ". This ratio is not a drift-adjusted stability measure.",
         "- ROC AUC, logistic: " + " → ".join(f"{auc.loc[c, 'logistic']:.3f}" for c in auc.index)
         + ". Three points from different cohorts neither establish stability nor show a significant decline.",
         "- Higher AP within each fold: " + ", ".join(f"{c} {v}" for c, v in best.items()) + ". "
         "No interval is given: the months contain " + "/".join(str(int(r["segments"][c])) for c in r["segments"].index)
         + " purchase-week segments (partial weeks at month edges included), too few for a week-level bootstrap, so the size of "
         "the logistic–GBM gap is not established here.",
         f"- Brier: logistic is below its fold's constant baseline in {lr_below} of {len(bs)} folds ("
         + ", ".join(f"{c} {bs.loc[c, 'logistic']:.4f} vs {bs.loc[c, 'baseline']:.4f}" for c in bs.index) + "). "
         "The constant itself is the fit late rate, so it is also miscalibrated when the month's late share moves.",
         "- Mean predicted vs observed late share (logistic): " + ", ".join(f"{c} {mp.loc[c, 'logistic']:.1%} vs {prev[c]:.1%}" for c in mp.index)
         + ". Over-prediction from stage 3 persists in every fold; probabilities are not usable as risk levels.",
         "- Late share differs a lot by month, and AP moves with it; compare AP with its own month's baseline, not across months.", "",
         "## Labels still unknown at each cut-off (excluded from the fit)", "", md_table(a), "",
         "Orders still in transit at T are disproportionately late. Excluding them is the price of not using future information; "
         "it also tilts the fit toward orders that arrived quickly.", "",
         "## How each evaluation month shrinks to the modelled population", "", md_table(p), "",
         "Purchases whose estimated week falls after the approved window are not in the population: " + cut + ". "
         "Median promised days, all purchases → modelled: " + med + ". The cut removes long-promise orders, so the later the fold, "
         "the more the evaluation group is selected. It also keeps only orders whose final outcome is A or L, which is known only "
         "after the fact. Treat the 2018-06-01 fold as the least comparable.", "",
         "## Limits", "",
         "- Not a new test: the months were already seen. No model or parameter was chosen from these results.",
         "- Three folds, one month each, no intervals, different cohorts: this shows whether a ranking signal is present in each month, "
         "not whether performance is stable or how large a difference is.",
         "- Population conditioned on a final A/L outcome; U, X and multi-seller orders are not scored.",
         "- `estimated_days` assumption (stored estimate = estimate shown at checkout) applies to every fold.", "",
         "## Blocking checks", "", md_table(r["checks"][["check", "expected", "actual", "pass"]]), ""]
    REPORT.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    r = main()
    print(r["metrics"][["cutoff", "model", "n", "prevalence", "average_precision", "brier", "precision_at_top", "recall_at_top"]].round(4).to_string(index=False))
