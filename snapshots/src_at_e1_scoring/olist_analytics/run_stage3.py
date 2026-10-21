"""Stage 3: purchase-time late-delivery risk model (offline simulation).

    PYTHONPATH=src python -m olist_analytics.run_stage3

Protocol
  1. Population: approved-window orders with final outcome A/L, single seller.
  2. Split by purchase time: train < 2018-01-01 <= dev < 2018-04-01 <= test.
  3. Tuning: fit each candidate on train rows whose label was known before 2018-01-01;
     score dev with seller features frozen at 2018-01-01; pick by dev AP using only
     dev labels delivered before the selection time 2018-04-01.
  4. Refit the chosen configs on train+dev rows whose label was known before 2018-04-01.
  5. Freeze. Evaluate test with seller features frozen at 2018-04-01. Test is not used
     to choose parameters; this revision re-evaluates a previously inspected test set.
Runs only on a current READY stage-1 release; publishes only if every blocking check passes.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .features import (CFG, FEATURES, LeakageError, assign_split, attach_seller, check_whitelist,
                       model_population, month_start, order_features, selection_labels_known_before)
from .gate import ReleaseBlocked, release_gate as shared_release_gate, retire_current_report, retire_stage4_outputs
from .io import ROOT, raw_dir, sha256
from .modeling import (calibration_table, candidates, gbm, importance, logistic, score_metrics,
                       week_bootstrap)
from .report import readiness

OUT = ROOT / "outputs"
S3 = OUT / "stage3"
REPORT = OUT / "stage3_model_report.md"
DATES = ["order_purchase_timestamp", "order_approved_at", "order_delivered_carrier_date",
         "order_delivered_customer_date", "order_estimated_delivery_date", "estimated_week", "shipping_limit_min"]


def release_gate(checks, report_path, reraise=True):
    return shared_release_gate(checks, report_path, reraise=reraise, blocked_path=S3 / "qa" / "RELEASE_BLOCKED.json")


def preconditions() -> dict:
    qa = OUT / "qa"
    problems = []
    if (qa / "RELEASE_BLOCKED.json").exists():
        problems.append("stage 1 is blocked")
    if not (OUT / "stage1_quality_report.md").exists():
        problems.append("no current stage-1 report")
    facts = json.loads((qa / "stage1_facts.json").read_text()) if (qa / "stage1_facts.json").exists() else None
    if facts is None:
        problems.append("stage-1 facts missing")
    else:
        state, why = readiness(facts["cohort_proposal"]["selected"])
        if state != "READY":
            problems.append(f"comparison readiness is {state}: {why}")
        changed = [s["file"] for s in facts.get("source_manifest", []) if sha256(raw_dir() / s["file"]) != s["sha256"]]
        problems += [f"source changed since stage 1: {c}" for c in changed]
    if problems:
        release_gate(pd.DataFrame({"check": problems, "expected": "ok", "actual": "failed", "pass": False}), REPORT)
    return facts


def load_mart() -> pd.DataFrame:
    return pd.read_csv(OUT / "marts" / "orders_mart.csv", parse_dates=DATES,
                       dtype={"customer_zip_code_prefix": str, "seller_zip_code_prefix": str})


def purchase_week(p: pd.Series) -> pd.Series:
    d = p.dt.normalize()
    return d - pd.to_timedelta(d.dt.weekday, unit="D")


def build_X(rows, base, history, snapshot_at, k):
    X, metas = attach_seller(rows, base.loc[rows.index], history, snapshot_at, k)
    X = X[FEATURES]
    check_whitelist(X)
    return X, metas


def main() -> dict:
    retire_current_report(REPORT)
    retire_stage4_outputs(OUT)                     # stage-4 pages and their UI/UAT evidence depend on this stage
    retire_current_report(OUT / "stage5_backtest_report.md")      # the backtest reuses this stage's outputs
    retire_current_report(OUT / "stage7_date_policy_report.md")   # so does the date-policy study
    retire_current_report(OUT / "stage7_monitoring_report.md")    # and its monitoring part
    retire_current_report(S3 / "independent_verification.json")   # must be re-derived for this run
    try:
        return _run()
    except ReleaseBlocked:
        raise
    except BaseException as e:
        release_gate(pd.DataFrame([{"check": "run completed", "expected": "no error",
                                    "actual": f"{type(e).__name__}: {e}"[:500], "pass": False}]), REPORT, reraise=False)
        raise


def _run() -> dict:
    facts1 = preconditions()
    sel = facts1["cohort_proposal"]["selected"]
    for d in (S3, S3 / "qa"):
        d.mkdir(parents=True, exist_ok=True)
    seed, k = CFG["models"]["seed"], CFG["seller_history"]["smoothing_k"]
    share, reps = CFG["evaluation"]["top_share"], CFG["evaluation"]["bootstrap"]["reps"]
    T1, T2 = pd.Timestamp(CFG["splits"]["dev"]["from"]), pd.Timestamp(CFG["splits"]["test"]["from"])

    mart = load_mart()
    history = mart[(mart.n_sellers == 1) & mart.single_seller_id.notna()]
    pop, steps = model_population(mart, sel["first_week"], sel["last_week"])
    pop["split"] = assign_split(pop.order_purchase_timestamp)
    pop["pweek"] = purchase_week(pop.order_purchase_timestamp)
    y_all = pop.is_late.astype(int)
    base = order_features(pop)

    # ---- label availability at each fit cut-off
    known_T1 = pop.order_delivered_customer_date < T1
    known_T2 = pop.order_delivered_customer_date < T2
    fit1 = pop[(pop.split == "train") & known_T1]
    fit2 = pop[pop.split.isin(["train", "dev"]) & known_T2]
    dev, test = pop[pop.split == "dev"], pop[pop.split == "test"]
    dev_select = selection_labels_known_before(dev, T2)
    if dev_select.empty or y_all[dev_select.index].nunique() < 2:
        raise LeakageError("no two-class, label-known development sample at selection time")
    excl = pd.DataFrame([
        {"fit": "tuning fit (train)", "cutoff": str(T1.date()), "rows_in_split": int((pop.split == "train").sum()),
         "label_known": len(fit1), "excluded_label_unknown": int(((pop.split == "train") & ~known_T1).sum()),
         "late_share_excluded": float(y_all[(pop.split == "train") & ~known_T1].mean())},
        {"fit": "final fit (train+dev)", "cutoff": str(T2.date()), "rows_in_split": int(pop.split.isin(["train", "dev"]).sum()),
         "label_known": len(fit2), "excluded_label_unknown": int((pop.split.isin(["train", "dev"]) & ~known_T2).sum()),
         "late_share_excluded": float(y_all[pop.split.isin(["train", "dev"]) & ~known_T2].mean())},
        {"fit": "model selection (dev)", "cutoff": str(T2.date()), "rows_in_split": len(dev),
         "label_known": len(dev_select), "excluded_label_unknown": len(dev)-len(dev_select),
         "late_share_excluded": float(y_all[dev.index.difference(dev_select.index)].mean())},
    ])

    # ---- features: training rows = month-start snapshots; evaluation rows = frozen at block start
    X_fit1, m1 = build_X(fit1, base, history, month_start(fit1.order_purchase_timestamp), k)
    X_dev, m2 = build_X(dev_select, base, history, pd.Series(T1, index=dev_select.index), k)
    X_fit2, m3 = build_X(fit2, base, history, month_start(fit2.order_purchase_timestamp), k)
    X_test, m4 = build_X(test, base, history, pd.Series(T2, index=test.index), k)
    X_test_monthly, m5 = build_X(test, base, history, month_start(test.order_purchase_timestamp), k)
    snapshots = pd.DataFrame([dict(use=u, **x) for u, ms in
                              [("tuning fit", m1), ("dev frozen", m2), ("final fit", m3), ("test frozen", m4),
                               ("test monthly (sensitivity)", m5)] for x in ms])

    # ---- tuning on dev
    tune = []
    for fam, params, make in candidates():
        mdl = make().fit(X_fit1, y_all[fit1.index])
        p = mdl.predict_proba(X_dev)[:, 1]
        tune.append({"family": fam, "params": json.dumps(params),
                     **score_metrics(y_all[dev_select.index], p, dev_select.pweek, share)})
    tune = pd.DataFrame(tune)
    best = {f: json.loads(g.sort_values("average_precision", ascending=False).iloc[0].params)
            for f, g in tune.groupby("family")}
    headline = tune.sort_values("average_precision", ascending=False).iloc[0].family   # chosen on dev, not test

    # ---- final fit on train+dev, frozen, scored once on test
    ytr, yte = y_all[fit2.index], y_all[test.index]
    final = {"logistic": logistic(best["logistic"]["C"]).fit(X_fit2, ytr),
             "gbm": gbm(best["gbm"]).fit(X_fit2, ytr)}
    prior = float(ytr.mean())
    scores = {"baseline": np.full(len(test), prior),
              **{n: m.predict_proba(X_test)[:, 1] for n, m in final.items()}}
    # A constant model has no ranking. Random capacity uses seeded tie-breaking;
    # its expected precision is prevalence, while a particular draw will vary.
    res = pd.DataFrame([{"model": n, **score_metrics(yte, s, test.pweek, share)} for n, s in scores.items()])
    random_order = np.random.default_rng(seed).permutation(len(test))
    from .modeling import top_share_by_week
    random_capacity = top_share_by_week(np.asarray(yte)[random_order], scores["baseline"][random_order],
                                        np.asarray(test.pweek)[random_order], share)
    for field, value in random_capacity.items():
        res.loc[res.model == "baseline", field] = value
    res["brier_skill_vs_baseline"] = 1 - res.brier / res.loc[res.model == "baseline", "brier"].iloc[0]

    # ---- uncertainty (purchase-week bootstrap) and calibration
    bs = week_bootstrap(yte, {"logistic": scores["logistic"], "gbm": scores["gbm"]}, test.pweek, reps, seed)
    bs["gbm_minus_logistic"] = bs.gbm - bs.logistic
    ci = bs.quantile([0.025, 0.5, 0.975]).T.reset_index().rename(columns={"index": "quantity", 0.025: "p2.5", 0.5: "p50", 0.975: "p97.5"})
    calib = pd.concat([calibration_table(yte, scores[n], CFG["evaluation"]["calibration_bins"]).assign(model=n)
                       for n in ("logistic", "gbm")], ignore_index=True)

    # ---- sensitivity: no estimated_days; monthly-refreshed seller features at test time
    sens = []
    num_wo = [c for c in CFG["features"]["numeric"] if c != "estimated_days"]
    wo = {"logistic": logistic(best["logistic"]["C"], num=num_wo), "gbm": gbm(best["gbm"], num=num_wo)}
    for n, mdl in wo.items():
        mdl.fit(X_fit2.drop(columns="estimated_days"), ytr)
        p = mdl.predict_proba(X_test.drop(columns="estimated_days"))[:, 1]
        sens.append({"variant": "without estimated_days", "model": n, **score_metrics(yte, p, test.pweek, share)})
    for n, mdl in final.items():
        p = mdl.predict_proba(X_test_monthly)[:, 1]
        sens.append({"variant": "test seller features refreshed monthly", "model": n, **score_metrics(yte, p, test.pweek, share)})
    sens = pd.DataFrame(sens)

    # ---- error analysis by month and customer state (test)
    seg = []
    dfe = test.assign(y=yte.values, p=scores[headline], m=test.order_purchase_timestamp.dt.to_period("M").astype(str))
    for col, name in (("m", "purchase month"), ("customer_state_reported", "customer state")):
        for g, x in dfe.groupby(col):
            if len(x) < 300 or x.y.sum() < 10:
                continue
            seg.append({"segment": name, "value": g, **score_metrics(x.y, x.p, x.pweek, share)})
    seg = pd.DataFrame(seg)

    imp = pd.concat([importance(final[n], X_test, yte, CFG["evaluation"]["permutation_repeats"], seed).assign(model=n)
                     for n in ("gbm", "logistic")], ignore_index=True)

    # ---- blocking checks
    hist_ok = all(pd.isna(r["max_label_delivery"]) or pd.Timestamp(r["max_label_delivery"]) < pd.Timestamp(r["T"])
                  for _, r in snapshots.iterrows())
    checks = pd.DataFrame([
        {"check": "population == train + dev + test", "expected": len(pop),
         "actual": int((pop.split == "train").sum() + len(dev) + len(test))},
        {"check": "splits ordered by purchase time (max train < min dev, max dev < min test)", "expected": True,
         "actual": bool(pop[pop.split == "train"].order_purchase_timestamp.max() < dev.order_purchase_timestamp.min()
                        and dev.order_purchase_timestamp.max() < test.order_purchase_timestamp.min())},
        {"check": "tuning fit uses only labels delivered before T1", "expected": True,
         "actual": bool((fit1.order_delivered_customer_date < T1).all())},
        {"check": "final fit uses only labels delivered before T2", "expected": True,
         "actual": bool((fit2.order_delivered_customer_date < T2).all())},
        {"check": "model selection uses only dev labels delivered before T2", "expected": True,
         "actual": bool((dev_select.order_delivered_customer_date < T2).all())},
        {"check": "every seller snapshot holds only labels delivered before its T", "expected": True, "actual": hist_ok},
        {"check": "no test row is in any fit", "expected": 0,
         "actual": int(len(set(test.index) & (set(fit1.index) | set(fit2.index))))},
        {"check": "feature matrix == whitelist (no forbidden column)", "expected": sorted(FEATURES),
         "actual": sorted(X_test.columns)},
        {"check": "baseline AP == test prevalence", "expected": round(float(yte.mean()), 10),
         "actual": round(float(res.loc[res.model == "baseline", "average_precision"].iloc[0]), 10)},
    ])
    checks["pass"] = checks.expected.astype(str) == checks.actual.astype(str)

    # ---- persist
    steps.to_csv(S3 / "population_steps.csv", index=False)
    split_tbl = (pop.groupby("split").agg(orders=("order_id", "size"), late=("is_late", "sum"),
                                          first_purchase=("order_purchase_timestamp", "min"),
                                          last_purchase=("order_purchase_timestamp", "max"))
                 .reindex(["train", "dev", "test"]).reset_index())
    split_tbl["late_rate"] = split_tbl.late / split_tbl.orders
    split_tbl.to_csv(S3 / "splits.csv", index=False)
    excl.to_csv(S3 / "label_availability.csv", index=False)
    snapshots.to_csv(S3 / "seller_snapshots.csv", index=False)
    tune.to_csv(S3 / "tuning_dev.csv", index=False)
    res.to_csv(S3 / "test_metrics.csv", index=False)
    ci.to_csv(S3 / "test_bootstrap_ci.csv", index=False)
    calib.to_csv(S3 / "calibration.csv", index=False)
    sens.to_csv(S3 / "sensitivity.csv", index=False)
    seg.to_csv(S3 / "segments.csv", index=False)
    imp.to_csv(S3 / "permutation_importance.csv", index=False)
    checks.to_csv(S3 / "stage3_checks.csv", index=False)
    pd.DataFrame({"order_id": test.order_id.values, "purchase_week": test.pweek.dt.date.values, "y": yte.values,
                  **{f"p_{n}": s for n, s in scores.items()}}).to_csv(S3 / "test_predictions.csv", index=False)

    lineage = {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "source_manifest": facts1["source_manifest"],
               "mart_sha256": sha256(OUT/"marts/orders_mart.csv"), "config_sha256": sha256(ROOT/"config/model.yaml"),
               "selection_cutoff": str(T2), "dev_selection_n": len(dev_select),
               "dev_selection_late": int(y_all[dev_select.index].sum()), "headline": headline,
               "parameters": best, "environment": {"pandas": pd.__version__, "numpy": np.__version__,
                   "sklearn": __import__("sklearn").__version__},
               "protocol_revision": "0.3.1: available development labels only", "checks_pass": bool(checks["pass"].all())}
    (S3/"lineage.json").write_text(json.dumps(lineage,indent=2))

    r = {"sel": sel, "steps": steps, "splits": split_tbl, "excl": excl, "snapshots": snapshots, "tune": tune,
         "best": best, "res": res, "ci": ci, "calib": calib, "sens": sens, "seg": seg, "imp": imp,
         "checks": checks, "prior": prior, "headline": headline,
         "selection": {"n": len(dev_select), "late": int(y_all[dev_select.index].sum()),
                       "prevalence": float(y_all[dev_select.index].mean()), "cutoff": str(T2.date())}}
    release_gate(checks, REPORT)
    from .report3 import write
    write(r, REPORT)
    return r


if __name__ == "__main__":
    r = main()
    print(r["checks"].to_string(index=False))
    print(r["res"].round(4).to_string(index=False))
