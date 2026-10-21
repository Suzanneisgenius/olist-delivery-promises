"""Supplementary simulation (synthetic data only; not part of the pre-registered E1 runs, touches no Olist data).

Question: when a split-conformal-style shift stops covering, is it because the delivery distribution changed over
time, or because at the freeze only orders that were already delivered (the fast ones) could be used?

One data-generating process, one fixed predictor, one calibration method (e1_models.shift / promise):
    x ~ U(0, 1)                      (a scaled 'distance')
    log Y* = a + b x + s e, e ~ N(0, 1);  Y = max(1, ceil(Y*))   (whole delivery days)
    predictor yhat(x) = exp(a + b x) (the conditional MEDIAN: deliberately not the 90% quantile, so calibration matters)
    shift: s_i = y_i - yhat_i, k = ceil((n + 1) q), Delta = s_(k); promise d(x) = max(1, ceil(yhat(x) + Delta))

Scenarios (same predictor, same calibration code, same evaluation size):
    S1 stable, complete   calibration and evaluation from the same distribution; every calibration label known
    S2 stable, censored   same distribution, but calibration orders are purchased uniformly over a W-day window and
                          only those delivered before the freeze (window end) are usable: t + Y < W
    S3a shift, slower     complete calibration labels; evaluation delivery times x 1.15
    S3b shift, faster     complete calibration labels; evaluation delivery times x 0.85

Each replication draws new calibration and evaluation samples. Reported: mean, SD and 5th-95th percentiles over
replications of coverage, mean promised days, the shift, and the usable calibration n.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from olist_analytics import e1_models as M

PARAMS = {"a": 2.2, "b": 0.5, "s": 0.45, "q": 0.90, "n_cal": 2000, "n_eval": 5000, "window_days": 90,
          "slower": 1.15, "faster": 0.85, "reps": 1000, "seed": 20261020}
SCENARIOS = ("S1 stable, complete labels", "S2 stable, only delivered-by-freeze labels",
             "S3a later deliveries 15% slower", "S3b later deliveries 15% faster")


def draw(n, rng, p, scale=1.0):
    x = rng.uniform(0, 1, n)
    ystar = np.exp(p["a"] + p["b"] * x + p["s"] * rng.standard_normal(n)) * scale
    return x, np.maximum(1, np.ceil(ystar))


def predictor(x, p):
    return np.exp(p["a"] + p["b"] * x)


def observed_by_freeze(y, rng, window_days):
    """Purchase time t ~ U(0, W); the label is usable at the freeze (time W) only if t + y < W."""
    t = rng.uniform(0, window_days, len(y))
    return t + y < window_days


def one_rep(rng, p):
    out = []
    xc, yc = draw(p["n_cal"], rng, p)
    keep = observed_by_freeze(yc, rng, p["window_days"])
    cal = {"S1": (xc, yc), "S2": (xc[keep], yc[keep])}
    d_full = M.shift(yc, predictor(xc, p), p["q"])
    d_cens = M.shift(cal["S2"][1], predictor(cal["S2"][0], p), p["q"])
    for name, delta, n_used, scale in [(SCENARIOS[0], d_full, len(yc), 1.0), (SCENARIOS[1], d_cens, int(keep.sum()), 1.0),
                                       (SCENARIOS[2], d_full, len(yc), p["slower"]), (SCENARIOS[3], d_full, len(yc), p["faster"])]:
        xe, ye = draw(p["n_eval"], rng, p, scale)
        d = M.promise(predictor(xe, p), delta)
        sc = M.policy_score(ye, d)
        out.append({"scenario": name, "shift_days": delta, "cal_n_used": n_used, "coverage": sc["coverage"],
                    "mean_promised_days": sc["mean_promised_days"]})
    return out


def run(p=PARAMS):
    rng = np.random.default_rng(p["seed"])
    reps = pd.DataFrame([dict(r, rep=i) for i in range(p["reps"]) for r in one_rep(rng, p)])
    q5, q95 = (lambda s: s.quantile(0.05)), (lambda s: s.quantile(0.95))
    summ = reps.groupby("scenario", sort=False).agg(
        coverage_mean=("coverage", "mean"), coverage_sd=("coverage", "std"),
        coverage_p05=("coverage", q5), coverage_p95=("coverage", q95),
        days_mean=("mean_promised_days", "mean"), days_p05=("mean_promised_days", q5), days_p95=("mean_promised_days", q95),
        shift_mean=("shift_days", "mean"), shift_p05=("shift_days", q5), shift_p95=("shift_days", q95),
        cal_n_mean=("cal_n_used", "mean"), share_reps_below_target=("coverage", lambda s: (s < p["q"]).mean()),
    ).reset_index()
    return reps, summ


def window_sensitivity(windows=(30, 45, 90, 180), p=PARAMS):
    """S1 vs S2 only, for different calibration-window lengths (shorter window = larger share still in transit)."""
    rows = []
    for w in windows:
        pw = dict(p, window_days=w)
        _, s = run(pw)
        for _, r in s[s.scenario.str.startswith(("S1", "S2"))].iterrows():
            rows.append({"window_days": w, **r.to_dict()})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="outputs/e1/sim")
    out = Path(ap.parse_args().out); out.mkdir(parents=True, exist_ok=True)
    reps, summ = run()
    reps.to_csv(out / "replications.csv", index=False)
    summ.to_csv(out / "summary.csv", index=False)
    (out / "params.json").write_text(json.dumps(PARAMS, indent=2))
    pd.set_option("display.width", 220)
    print(summ.round(4).to_string(index=False))
    sens = window_sensitivity()
    sens.to_csv(out / "window_sensitivity.csv", index=False)
    print(sens[["window_days", "scenario", "coverage_mean", "coverage_p05", "coverage_p95", "days_mean", "shift_mean",
                "cal_n_mean", "share_reps_below_target"]].round(4).to_string(index=False))

