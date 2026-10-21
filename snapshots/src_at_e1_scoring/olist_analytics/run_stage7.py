"""Stage 7 (parts 1-2): can promised delivery dates be tighter and still reliable?

    PYTHONPATH=src python -m olist_analytics.run_stage7

Pre-registered in config/date_policy.yaml (SHA-256 recorded in outputs/stage7/PREREGISTRATION_SHA256.txt).
Policies are fitted and calibrated with information known at the freeze time (2018-04-01), frozen, and scored
on later purchases. Exploratory extension: the data were already inspected in stages 1-6.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .date_policy import (apply_state_policy, conformal_shift, monthly_unreliable, olist_promise_days,
                          predicted_days, quantile_regression, required_days, score, state_quantile_policy,
                          to_promise, verdict_complex_over_baseline)
from .features import CFG as CFG3, attach_seller, model_population, month_start, order_features
from .gate import ReleaseBlocked, release_gate as shared_release_gate, retire_current_report
from .io import ROOT, load_yaml, sha256

OUT = ROOT / "outputs"
S7 = OUT / "stage7"
REPORT = OUT / "stage7_date_policy_report.md"
MONITOR_REPORT = OUT / "stage7_monitoring_report.md"     # part 3 depends on these verdicts
CFG_PATH = ROOT / "config" / "date_policy.yaml"


def release_gate(checks, reraise=True):
    return shared_release_gate(checks, REPORT, reraise=reraise, blocked_path=S7 / "qa" / "RELEASE_BLOCKED.json")


def registered_sha() -> str:
    return (S7 / "PREREGISTRATION_SHA256.txt").read_text().split()[0]


def split_rows(pop: pd.DataFrame, cfg: dict) -> dict:
    T = pd.Timestamp(cfg["freeze_at"])
    P, D = pop.order_purchase_timestamp, pop.order_delivered_customer_date
    w = cfg["windows"]
    known = D < T
    between = lambda a, b: (P >= pd.Timestamp(a)) & (P < pd.Timestamp(b))
    return {"fit": pop[(P < pd.Timestamp(w["fit"]["to"])) & known],
            "cal_A": pop[between(w["calibration_A"]["from"], w["calibration_A"]["to"]) & known],
            "cal_B": pop[between(w["calibration_B"]["from"], w["calibration_B"]["to"]) & known],
            "eval": pop[P >= pd.Timestamp(w["evaluation"]["from"])]}


def breakdown(rows: pd.DataFrame, req: pd.Series, promised: pd.Series, by: pd.Series, name: str) -> pd.DataFrame:
    out = []
    for g, idx in rows.groupby(by.loc[rows.index]).groups.items():
        out.append({name: str(g), **score(req.loc[idx], promised.loc[idx])})
    return pd.DataFrame(out)


def main() -> dict:
    retire_current_report(REPORT)
    retire_current_report(MONITOR_REPORT)
    try:
        return _run()
    except ReleaseBlocked:
        raise
    except BaseException as e:
        release_gate(pd.DataFrame([{"check": "run completed", "expected": "no error",
                                    "actual": f"{type(e).__name__}: {e}"[:500], "pass": False}]), reraise=False)
        raise


def _run() -> dict:
    cfg = load_yaml("date_policy.yaml")
    (S7 / "qa").mkdir(parents=True, exist_ok=True)
    pre = pd.DataFrame([
        {"check": "config matches the registered SHA-256", "expected": registered_sha(), "actual": sha256(CFG_PATH)},
        {"check": "stage 3 report is current", "expected": True, "actual": (OUT / "stage3_model_report.md").exists()},
    ])
    pre["pass"] = pre.expected.astype(str) == pre.actual.astype(str)
    release_gate(pre)

    from .run_stage3 import load_mart
    sel = json.loads((OUT / "qa" / "stage1_facts.json").read_text())["cohort_proposal"]["selected"]
    mart = load_mart()
    history = mart[(mart.n_sellers == 1) & mart.single_seller_id.notna()]
    pop, _ = model_population(mart, sel["first_week"], sel["last_week"])
    req, olist = required_days(pop), olist_promise_days(pop)
    base = order_features(pop)
    rows = split_rows(pop, cfg)
    T = pd.Timestamp(cfg["freeze_at"])
    k = CFG3["seller_history"]["smoothing_k"]
    f = cfg["features"]
    cols = f["numeric"] + f["categorical"]
    snap_at = {"fit": month_start(rows["fit"].order_purchase_timestamp),
               "cal_A": pd.Series(pd.Timestamp(cfg["windows"]["calibration_A"]["from"]), index=rows["cal_A"].index),
               "cal_B": pd.Series(pd.Timestamp(cfg["windows"]["calibration_B"]["from"]), index=rows["cal_B"].index),
               "eval": pd.Series(T, index=rows["eval"].index)}
    X, metas = {}, []
    for name, r in rows.items():
        x, m = attach_seller(r, base.loc[r.index], history, snap_at[name], k)
        X[name] = x[cols]
        metas += [dict(use=name, **mm) for mm in m]
    ev = rows["eval"]
    month = ev.order_purchase_timestamp.dt.to_period("M").astype(str)
    state = pop.customer_state_reported

    olist_cov_A = float((req.loc[rows["cal_A"].index] <= olist.loc[rows["cal_A"].index]).mean())
    targets = {"0.90": 0.90, "0.95": 0.95, "olist_matched": round(olist_cov_A, 4)}
    b0_train = pd.concat([rows["fit"], rows["cal_A"]])

    overall, monthly, states, shifts, verdicts = [], [], [], [], {}
    preds_store, residuals = {}, []
    olist_eval = olist.loc[ev.index]
    o_score = score(req.loc[ev.index], olist_eval)
    for tname, lvl in targets.items():
        b0 = state_quantile_policy(req.loc[b0_train.index], state.loc[b0_train.index], lvl, 300)
        qr = quantile_regression(lvl, f["numeric"], f["log_transform"], f["categorical"], f["categorical_min_count"])
        qr.fit(X["fit"], np.log1p(req.loc[rows["fit"].index]))
        pred = {n: predicted_days(qr, X[n]) for n in ("cal_A", "cal_B", "eval")}
        sA = conformal_shift(req.loc[rows["cal_A"].index].to_numpy(), pred["cal_A"], lvl)
        sB = conformal_shift(req.loc[rows["cal_B"].index].to_numpy(), pred["cal_B"], lvl)
        shifts += [{"target": tname, "level": lvl, "calibration": "A", "n": len(rows["cal_A"]), "shift_days": sA},
                   {"target": tname, "level": lvl, "calibration": "B", "n": len(rows["cal_B"]), "shift_days": sB}]
        promised = {
            "B0_state_quantile": apply_state_policy(b0, state.loc[ev.index]),
            "Q1_quantile_regression": pd.Series(to_promise(pred["eval"]), index=ev.index),
            "Q2_qr_conformal_A": pd.Series(to_promise(pred["eval"] + sA), index=ev.index),
            "Q2_qr_conformal_B": pd.Series(to_promise(pred["eval"] + sB), index=ev.index),
            "Olist_promise": olist_eval,
        }
        preds_store[tname] = {"pred_eval": pred["eval"], "promised": promised}
        for cn in ("cal_A", "cal_B"):
            residuals.append(pd.DataFrame({"order_id": rows[cn].order_id.values, "calibration": cn[-1], "target": tname,
                                           "required_days": req.loc[rows[cn].index].values,
                                           "predicted_days": pred[cn], "score": req.loc[rows[cn].index].values - pred[cn]}))
        for pname, p in promised.items():
            overall.append({"target": tname, "level": lvl, "policy": pname, **score(req.loc[ev.index], p)})
            mb = breakdown(ev, req, p, month, "month").assign(target=tname, level=lvl, policy=pname)
            monthly.append(mb)
            sb = breakdown(ev, req, p, state, "state").assign(target=tname, level=lvl, policy=pname)
            states.append(sb[sb.orders >= cfg["segments"]["report_state_if_evaluation_orders_at_least"]])
        res = {r["policy"]: r for r in overall if r["target"] == tname}
        mth = pd.concat(monthly)
        mth_t = mth[mth.target == tname]
        gap = lambda pol: float((mth_t[mth_t.policy == pol].coverage - lvl).abs().mean() * 100)
        verdicts[tname] = {
            "level": lvl,
            "Q2A_vs_B0": verdict_complex_over_baseline(res["Q2_qr_conformal_A"], res["B0_state_quantile"]),
            "Q1_vs_B0": verdict_complex_over_baseline(res["Q1_quantile_regression"], res["B0_state_quantile"]),
            "months_unreliable": {p: monthly_unreliable(mth_t[mth_t.policy == p], lvl)
                                  for p in ("B0_state_quantile", "Q1_quantile_regression", "Q2_qr_conformal_A", "Q2_qr_conformal_B")},
            "calibration_mean_abs_monthly_gap_pts": {"A": gap("Q2_qr_conformal_A"), "B": gap("Q2_qr_conformal_B")},
        }
        verdicts[tname]["calibration_A_better"] = verdicts[tname]["calibration_mean_abs_monthly_gap_pts"]["A"] < \
            verdicts[tname]["calibration_mean_abs_monthly_gap_pts"]["B"]
        if tname == "olist_matched":
            for pol in ("B0_state_quantile", "Q1_quantile_regression", "Q2_qr_conformal_A"):
                v = verdict_complex_over_baseline(res[pol], o_score)
                tighter = v.pop("keep_complex")
                verdicts[tname][f"{pol}_vs_Olist"] = {**v, "shorter_with_coverage_loss_within_tolerance": tighter}

    # per-order evidence so the summaries can be re-derived without refitting
    orders = pd.DataFrame({"order_id": ev.order_id.values, "purchase_month": month.values,
                           "customer_state": state.loc[ev.index].values, "required_days": req.loc[ev.index].values})
    for tname, st in preds_store.items():
        orders[f"q_pred_days_{tname}"] = st["pred_eval"]
        for pname, prom in st["promised"].items():
            if pname != "Olist_promise" or tname == "0.90":
                orders[f"{pname}_{tname}" if pname != "Olist_promise" else "Olist_promise"] = np.asarray(prom)
    (S7 / "orders").mkdir(exist_ok=True)
    orders.to_csv(S7 / "orders" / "evaluation_promises.csv", index=False)
    pd.concat(residuals, ignore_index=True).to_csv(S7 / "orders" / "calibration_scores.csv", index=False)

    overall, monthly, states = pd.DataFrame(overall), pd.concat(monthly, ignore_index=True), pd.concat(states, ignore_index=True)

    # descriptive curves (not used for decisions)
    curves = []
    p90 = preds_store["0.90"]["pred_eval"]
    for c in range(-5, 11):
        curves.append({"curve": "Q2 shift sweep (0.90 model)", "param": c, **score(req.loc[ev.index], to_promise(p90 + c))})
    for lvl in np.round(np.arange(0.80, 0.981, 0.02), 2):
        b0 = state_quantile_policy(req.loc[b0_train.index], state.loc[b0_train.index], float(lvl), 300)
        curves.append({"curve": "B0 level sweep", "param": float(lvl), **score(req.loc[ev.index], apply_state_policy(b0, state.loc[ev.index]))})
    for c in range(-14, 3):
        curves.append({"curve": "Olist promise + c days", "param": c, **score(req.loc[ev.index], np.maximum(olist_eval + c, 1))})
    curves = pd.DataFrame(curves)

    # phase-0 descriptive tables (saved with the run)
    slack = olist - req
    ph_states = (pd.DataFrame({"state": state, "req": req, "olist": olist, "slack": slack, "late": pop.is_late})
                 .groupby("state").agg(orders=("req", "size"), required_median=("req", "median"),
                                       required_p90=("req", lambda s: s.quantile(0.9)), promise_median=("olist", "median"),
                                       slack_median=("slack", "median"), late_rate=("late", "mean")).reset_index())

    hist_ok = all(mm["max_label_delivery"] is None or pd.Timestamp(mm["max_label_delivery"]) < pd.Timestamp(mm["T"]) for mm in metas)
    used = set().union(*[set(x.columns) for x in X.values()])
    checks = pd.DataFrame([
        {"check": "fit and calibration labels delivered before the freeze", "expected": True,
         "actual": bool(all((rows[n].order_delivered_customer_date < T).all() for n in ("fit", "cal_A", "cal_B")))},
        {"check": "fit, calibration and evaluation windows do not overlap", "expected": 0,
         "actual": int(sum(len(set(rows[a].index) & set(rows[b].index)) for a, b in
                           [("fit", "cal_A"), ("fit", "cal_B"), ("cal_A", "cal_B"), ("fit", "eval"), ("cal_A", "eval"), ("cal_B", "eval")]))},
        {"check": "Olist's own estimate is not a model input", "expected": False, "actual": "estimated_days" in used},
        {"check": "every seller snapshot holds only labels delivered before its time", "expected": True, "actual": hist_ok},
        {"check": "Olist promise coverage on evaluation == 1 - stage-3 late rate", "expected": True,
         "actual": bool(np.isclose(o_score["coverage"], 1 - ev.is_late.mean()))},
        {"check": "required_days > olist_promise_days exactly for late orders", "expected": True,
         "actual": bool(((req > olist) == pop.is_late.astype(bool)).all())},
    ])
    checks["pass"] = checks.expected.astype(str) == checks.actual.astype(str)
    allchk = pd.concat([pre, checks], ignore_index=True)

    for name, df in [("policy_results", overall), ("monthly", monthly), ("states", states), ("curves", curves),
                     ("conformal_shifts", pd.DataFrame(shifts)), ("phase0_states", ph_states), ("stage7_checks", allchk)]:
        df.to_csv(S7 / f"{name}.csv", index=False)
    split_info = {n: {"orders": len(r), "late_rate": float(r.is_late.mean()),
                      "first_purchase": str(r.order_purchase_timestamp.min()), "last_purchase": str(r.order_purchase_timestamp.max())}
                  for n, r in rows.items()}
    (S7 / "verdicts.json").write_text(json.dumps({"targets": targets, "olist_coverage_on_calibration_A": olist_cov_A,
                                                  "splits": split_info, "verdicts": verdicts}, indent=2, default=str))
    (S7 / "lineage.json").write_text(json.dumps({
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "config_sha256": sha256(CFG_PATH),
        "registered_sha256": registered_sha(), "mart_sha256": sha256(OUT / "marts" / "orders_mart.csv"),
        "environment": {"pandas": pd.__version__, "numpy": np.__version__, "sklearn": __import__("sklearn").__version__},
        "checks_pass": bool(allchk["pass"].all())}, indent=2))
    release_gate(allchk)
    r = {"overall": overall, "monthly": monthly, "states": states, "curves": curves, "shifts": pd.DataFrame(shifts),
         "verdicts": verdicts, "targets": targets, "splits": split_info, "checks": allchk, "olist": o_score}
    write_report(r)
    return r


def write_report(r: dict) -> None:
    from .report import md_table
    pct = lambda v: f"{v * 100:.1f}%"
    o = r["overall"].copy()
    t = o[["target", "policy", "orders", "coverage", "mean_promised_days", "median_promised_days", "mean_overrun_days_when_missed"]].copy()
    t["coverage"] = t.coverage.map(pct)
    for c in ("mean_promised_days", "mean_overrun_days_when_missed"):
        t[c] = t[c].map(lambda v: f"{v:.2f}")
    m = r["monthly"]
    mt = m[m.policy.isin(["B0_state_quantile", "Q2_qr_conformal_A", "Q2_qr_conformal_B", "Olist_promise"])].pivot_table(
        index=["target", "policy"], columns="month", values="coverage").map(pct).reset_index()
    L = ["# Stage 7 — Promised-Date Policies (parts 1–2)", "",
         "> Exploratory extension, pre-registered in `config/date_policy.yaml` (SHA-256 in `outputs/stage7/PREREGISTRATION_SHA256.txt`). "
         "Policies are fitted and calibrated with information known at 2018-04-01, frozen, and scored on purchases from 2018-04-01. "
         "Population: single-seller orders with a final on-time/late outcome — results do not cover canceled or unconfirmed orders.", "",
         "## Splits", "", md_table(pd.DataFrame(r["splits"]).T.reset_index().rename(columns={"index": "rows"})), "",
         "## Overall results (evaluation orders)", "", md_table(t), "",
         "## Conformal shifts (days added to the regression prediction)", "", md_table(r["shifts"].round(2)), "",
         "## Monthly coverage", "", md_table(mt), "",
         "## Decision rules (as registered)", "", "```json", json.dumps(r["verdicts"], indent=2, default=str), "```", "",
         "## Blocking checks", "", md_table(r["checks"][["check", "expected", "actual", "pass"]]), ""]
    REPORT.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    r = main()
    print(r["overall"].round(4).to_string(index=False))
    print(json.dumps(r["verdicts"], indent=1, default=str))
