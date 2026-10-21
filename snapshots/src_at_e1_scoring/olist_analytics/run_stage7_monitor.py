"""Stage 7 part 3: what drop should trigger a review of a frozen promised-date policy?

    PYTHONPATH=src python -m olist_analytics.run_stage7_monitor

Runs after parts 1-2 (run_stage7). Rules are the registered `monitoring` block of config/date_policy.yaml;
readings M1-M7 are logged in docs/DATE_POLICY_DECISIONS.md. Alarms trigger human review only.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from . import monitoring as mon
from .date_policy import apply_state_policy, olist_promise_days, required_days, state_quantile_policy
from .features import model_population
from .gate import ReleaseBlocked, release_gate as shared_release_gate, retire_current_report
from .io import load_yaml, sha256
from .run_stage7 import CFG_PATH, OUT, REPORT as PART12_REPORT, S7, registered_sha, split_rows

M = S7 / "monitoring"
REPORT = OUT / "stage7_monitoring_report.md"
TARGET, P1_GAP = 0.90, 0.05


def release_gate(checks, reraise=True):
    return shared_release_gate(checks, REPORT, reraise=reraise, blocked_path=M / "qa" / "RELEASE_BLOCKED.json")


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
    cfg = load_yaml("date_policy.yaml")
    (M / "qa").mkdir(parents=True, exist_ok=True)
    verdicts = json.loads((S7 / "verdicts.json").read_text()) if (S7 / "verdicts.json").exists() else {}
    v90 = verdicts.get("verdicts", {}).get("0.90", {})
    kept_b0 = (v90.get("Q2A_vs_B0", {}).get("keep_complex") is False and v90.get("Q1_vs_B0", {}).get("keep_complex") is False)
    pre = pd.DataFrame([
        {"check": "config matches the registered SHA-256", "expected": registered_sha(), "actual": sha256(CFG_PATH)},
        {"check": "parts 1-2 report is current", "expected": True, "actual": PART12_REPORT.exists()},
        {"check": "parts 1-2 kept the simple state rule (B0) at target 0.90", "expected": True, "actual": kept_b0},
    ])
    pre["pass"] = pre.expected.astype(str) == pre.actual.astype(str)
    release_gate(pre)

    from .run_stage3 import load_mart
    sel = json.loads((OUT / "qa" / "stage1_facts.json").read_text())["cohort_proposal"]["selected"]
    pop, _ = model_population(load_mart(), sel["first_week"], sel["last_week"])
    req, olist = required_days(pop), olist_promise_days(pop)
    rows = split_rows(pop, cfg)
    ev = rows["eval"]
    state = pop.customer_state_reported
    train = pd.concat([rows["fit"], rows["cal_A"]])
    b0 = state_quantile_policy(req.loc[train.index], state.loc[train.index], TARGET, 300)
    b0_eval = apply_state_policy(b0, state.loc[ev.index])
    olist_target = float(verdicts["targets"]["olist_matched"])
    mc = cfg["monitoring"]["simulation"]
    rng = np.random.default_rng(cfg["seed"])

    # --- calibrate h for each monitored series (nominal Bernoulli in-control, reading M5)
    n = mc["orders_per_week"]
    cal = {"B0_0.90": mon.calibrate_h(1 - TARGET, 1 - TARGET + P1_GAP, n, 52, rng),
           "Olist_matched": mon.calibrate_h(1 - olist_target, 1 - olist_target + P1_GAP, n, 52, rng)}
    # exact in-control burden of each rule under the same binomial null (1,200 orders/week)
    nominal = {k: {"single_week_llr": mon.nominal_arl_single_week(1 - t, 1 - t + P1_GAP, n),
                   "threshold": mon.nominal_arl_threshold(t, n)}
               for k, t in (("B0_0.90", TARGET), ("Olist_matched", olist_target))}

    # --- historical replay
    replay = []
    series = {"B0_0.90": (ev, b0_eval, TARGET, "evaluation (out of sample)"),
              "Olist_matched": (ev, olist.loc[ev.index], olist_target, "evaluation (out of sample)"),
              "Olist_matched_full_period": (pop, olist, olist_target, "whole population (in-sample illustration)")}
    for name, (r, p, tgt, scope) in series.items():
        w = mon.weekly_cohorts(r.order_purchase_timestamp, req.loc[r.index], p)
        key = "B0_0.90" if name.startswith("B0") else "Olist_matched"
        p0 = 1 - tgt
        stat, c_alarm = mon.cusum(w.misses, w.orders, p0, p0 + P1_GAP, cal[key]["h"])
        w = w.assign(series=name, scope=scope, target=tgt, cusum=stat, cusum_alarm=c_alarm,
                     threshold_alarm=mon.threshold_alarms(w.coverage, w.orders, tgt))
        replay.append(w)
    replay = pd.concat(replay, ignore_index=True)

    # --- bootstrap simulation under the frozen B0 policy (registered)
    req_ev, prom_ev = req.loc[ev.index].to_numpy(), b0_eval.to_numpy()
    p0, p1, h = 1 - TARGET, 1 - TARGET + P1_GAP, cal["B0_0.90"]["h"]
    sims, summary = {}, []
    for sc in mc["scenarios"]:
        sims[sc] = mon.simulate(req_ev, prom_ev, sc, p0=p0, p1=p1, h=h, target=TARGET, weeks=mc["weeks"], n=n,
                                reps=mc["replications"], rng=rng)
        summary += [dict(design="order bootstrap (registered)", **s) for s in mon.summarize(sims[sc], sc, mc["weeks"])]

    # --- exploratory (M7): between-week noise
    wk_ev = replay[replay.series == "B0_0.90"]
    ev_week = (ev.order_purchase_timestamp.dt.normalize() - pd.to_timedelta(ev.order_purchase_timestamp.dt.weekday, unit="D"))
    pos = pd.Series(np.arange(len(ev)), index=ev.index)
    big = wk_ev[wk_ev.orders >= 200].week
    pools = [pos[ev_week == wk].to_numpy() for wk in big]
    wsim = mon.simulate(req_ev, prom_ev, "none", p0=p0, p1=p1, h=h, target=TARGET, weeks=mc["weeks"], n=n,
                        reps=mc["replications"], rng=rng, week_pools=pools)
    summary += [dict(design="week-resampled (exploratory)", **s) for s in mon.summarize(wsim, "none", mc["weeks"])]
    disp = {"B0_0.90_evaluation": mon.dispersion_ratio(wk_ev),
            "Olist_full_period": mon.dispersion_ratio(replay[replay.series == "Olist_matched_full_period"])}
    summary = pd.DataFrame(summary)
    if all(c["h"] == 0 for c in cal.values()):     # h = 0 makes the CUSUM memoryless: name it for what it is
        summary["rule"] = summary.rule.replace({"cusum": "single_week_llr (CUSUM at h=0)"})

    # mean weekly path for the chart (coverage and CUSUM alarm share by week)
    path = pd.concat([s.groupby("week").agg(mean_coverage=("coverage", "mean"),
                                            p05_coverage=("coverage", lambda x: x.quantile(0.05)),
                                            cusum_alarm_share=("cusum_alarm", "mean"),
                                            threshold_alarm_share=("threshold_alarm", "mean")).reset_index().assign(scenario=sc)
                      for sc, s in sims.items()], ignore_index=True)

    # --- blocking checks
    b0_cov = float((req_ev <= prom_ev).mean())
    part12 = pd.read_csv(S7 / "policy_results.csv")
    ref = float(part12[(part12.target == "0.90") & (part12.policy == "B0_state_quantile")].coverage.iloc[0])
    checks = pd.DataFrame([
        {"check": "B0 rebuilt here reproduces parts 1-2 coverage", "expected": True, "actual": bool(np.isclose(b0_cov, ref))},
        {"check": "weekly replay counts every evaluation order once", "expected": len(ev),
         "actual": int(wk_ev.orders.sum())},
        {"check": "h is the attainable value (h >= 0) closest to an in-control ARL of 52 weeks", "expected": True,
         "actual": all(c["h"] >= 0 and (nominal[k]["single_week_llr"]["arl_weeks"] >= 52 if c["h"] == 0
                                        else abs(c["restricted_mean_run_length_weeks"] - 52) / 52 < 0.10)
                       for k, c in cal.items())},
        {"check": "h = 0: simulated restricted mean agrees with the exact geometric ARL (within 10%, given censoring)",
         "expected": True,
         "actual": all(c["h"] != 0 or abs(c["restricted_mean_run_length_weeks"] - _restricted(nominal[k]["single_week_llr"]
                                                                                                ["weekly_alarm_prob"], c["cap_weeks"]))
                       / c["restricted_mean_run_length_weeks"] < 0.10 for k, c in cal.items())},
        {"check": "'none' scenario keeps the evaluation coverage (bootstrap sanity, +/- 0.5 pt)", "expected": True,
         "actual": bool(abs(sims["none"].coverage.mean() - b0_cov) < 0.005)},
        {"check": "each scenario has replications x weeks simulated weeks", "expected": True,
         "actual": all(len(s) == mc["replications"] * mc["weeks"] and s.rep.nunique() == mc["replications"]
                       for s in sims.values())},
    ])
    checks["pass"] = checks.expected.astype(str) == checks.actual.astype(str)
    allchk = pd.concat([pre, checks], ignore_index=True)

    for name, df in [("replay_weekly", replay), ("simulation_summary", summary), ("simulation_paths", path),
                     ("checks", allchk)]:
        df.to_csv(M / f"{name}.csv", index=False)
    info = {"h_calibration": cal, "nominal_in_control_arl": nominal, "dispersion_ratio": disp, "b0_eval_coverage": b0_cov, "olist_target": olist_target,
            "b0_promise_by_state": b0["by_state"], "b0_overall": b0["overall"]}
    (M / "monitoring.json").write_text(json.dumps(info, indent=2, default=float))
    (M / "lineage.json").write_text(json.dumps({
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "config_sha256": sha256(CFG_PATH),
        "part12_verdicts_sha256": sha256(S7 / "verdicts.json"), "mart_sha256": sha256(OUT / "marts" / "orders_mart.csv"),
        "checks_pass": bool(allchk["pass"].all())}, indent=2))
    release_gate(allchk)
    r = {"replay": replay, "summary": summary, "path": path, "info": info, "checks": allchk}
    write_report(r)
    return r


def _restricted(q: float, cap: int) -> float:
    """E[min(T, cap + 1)] for a geometric first-alarm week T with weekly probability q."""
    return float((1 - (1 - q) ** (cap + 1)) / q)


def write_report(r: dict) -> None:
    from .report import md_table
    s = r["summary"].copy()
    for c in s.columns:
        if s[c].dtype == float:
            s[c] = s[c].round(3)
    rp = r["replay"]
    alarms = rp[(rp.cusum_alarm) | (rp.threshold_alarm)][["series", "week", "orders", "coverage", "cusum", "cusum_alarm",
                                                         "threshold_alarm", "final_at"]].copy()
    alarms["coverage"] = (alarms.coverage * 100).round(1)
    alarms["cusum"] = alarms.cusum.round(2)
    i = r["info"]
    def _row(series, rule, v):
        if rule == "single_week_llr":
            return {"series": series, "rule": "single-week LLR (CUSUM at h=0)",
                    "one-week crossing prob.": f"{v['weekly_alarm_prob']:.4g}",
                    "full alarm condition": f"this week >= {v['alarm_if_misses_at_least']} misses of 1,200",
                    "exact ARL (weeks)": f"{v['arl_weeks']:.6g}",
                    "assumption": "independent binomial weeks at p0; memoryless, so ARL = 1/q"}
        return {"series": series, "rule": "threshold (2 consecutive low weeks, reset)",
                "one-week crossing prob.": f"{v['weekly_low_prob']:.4g}",
                "full alarm condition": f"2 consecutive weeks each >= {v['low_week_if_misses_at_least']} misses of 1,200",
                "exact ARL (weeks)": f"{v['arl_weeks']:.5g}",
                "assumption": "independent binomial weeks at p0; ARL = (1+q)/q^2, q = one-week crossing prob."}
    nom = pd.DataFrame([_row(k, rule, v) for k, d in i["nominal_in_control_arl"].items() for rule, v in d.items()])
    L = ["# Stage 7 — Monitoring a Frozen Promised-Date Policy (part 3)", "",
         "> Exploratory extension. Rules registered in `config/date_policy.yaml` (`monitoring`); readings M1–M8 and "
         "deviation D1 in `docs/DATE_POLICY_DECISIONS.md`. Alarms trigger human review only — no automatic "
         "recalibration. Monitored policy: B0 (per-state quantile) at target 0.90, the policy parts 1–2 kept.", "",
         "> **The registered 52-week in-control ARL is unattainable** with 1,200 orders/week, so h = 0 is used. At h = 0 the "
         "CUSUM never carries evidence across weeks: it is a **single-week log-likelihood-ratio rule**. Its exact in-control "
         "burden differs from the threshold rule's by many orders of magnitude, so the simulation below does **not** show that "
         "one method is better than the other.", "",
         "## Exact in-control burden (independent binomial weeks, 1,200 orders)", "",
         "The crossing probability is for one week. For the threshold rule it is NOT the rule's weekly alarm probability: "
         "an alarm needs two consecutive crossings, and its long-run alarm frequency is 1 / ARL.", "", md_table(nom), "",
         "## h calibration by simulation (restricted mean: runs without an alarm by the cap count as cap + 1)", "",
         md_table(pd.DataFrame(i["h_calibration"]).T.reset_index().rename(columns={"index": "series"}).round(4)), "",
         f"B0 coverage on evaluation orders: {i['b0_eval_coverage'] * 100:.2f}% (target 90%). "
         f"Olist matched target: {i['olist_target'] * 100:.2f}%.", "",
         "## Simulation (500 replications × 30 weeks × 1,200 orders; order bootstrap)", "",
         "Calendar delay = days from the change start (Monday) to the date the alarm week is final "
         "(its Sunday + longest promise + 1 day).", "", md_table(s), "",
         "## Over-dispersion (exploratory)", "",
         "Observed week-to-week variance of coverage ÷ binomial variance (1 = order-level noise only): "
         + ", ".join(f"{k} = {v:.1f}" for k, v in i["dispersion_ratio"].items()), "",
         "## Historical replay — weeks with an alarm", "",
         "Computed per purchase week, then labelled with `final_at`; weeks are not re-ordered by information arrival. "
         "This is harmless for the memoryless h = 0 rule but would matter for any rule with state.", "",
         md_table(alarms) if len(alarms) else "No alarms.", "",
         "## Blocking checks", "", md_table(r["checks"][["check", "expected", "actual", "pass"]]), ""]
    REPORT.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    r = main()
    print(r["summary"].round(3).to_string(index=False))
    print(json.dumps({k: r["info"][k] for k in ("h_calibration", "nominal_in_control_arl", "dispersion_ratio")}, indent=1))
