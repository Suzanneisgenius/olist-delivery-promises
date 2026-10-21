"""Supplementary simulation, run 2 (PAIRED sensitivity run). Run 1 (scripts/e1_calibration_sim.py, outputs/e1/sim/)
is kept unchanged. Synthetic data only; explains mechanisms, proves nothing about Olist.

Differences from run 1 (where S1/S2 already shared the calibration queue but every scenario drew its own evaluation
orders): within each replication
  * one calibration queue (x, e, purchase time t); S2 uses its delivered-by-freeze subset (t + Y < W);
  * one evaluation sample (x, e) shared by ALL scenarios; S3a / S3b only rescale delivery time before rounding:
    Y = max(1, ceil(exp(a + b x + s e) * scale)) with the same x and e;
  * optional diagnostic S2-size: a uniformly random subset of the full queue with the SAME size as S2's delivered
    subset (separates "fewer labels" from "only the fast labels").
Same predictor (conditional median) and same calibration code (e1_models.shift / promise): the shift uses integer
Y minus the UNROUNDED prediction; promise = max(1, ceil(yhat + shift - 1e-9)); covered = Y <= promise.
Reported: per-replication values, paired differences vs S1, means with Monte Carlo standard errors (SD / sqrt(R)),
and, separately, 5th-95th percentiles across replications.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from olist_analytics import e1_models as M

PARAMS = {"a": 2.2, "b": 0.5, "s": 0.45, "q": 0.90, "n_cal": 2000, "n_eval": 5000, "window_days": 90,
          "slower": 1.15, "faster": 0.85, "reps": 1000, "seed": 20261021}
SCEN = ["S1 stable, complete labels", "S2 stable, only delivered-by-freeze labels",
        "S2-size random subset, same n as S2 (diagnostic)", "S3a later deliveries 15% slower",
        "S3b later deliveries 15% faster"]


def days(x, e, p, scale=1.0):
    return np.maximum(1, np.ceil(np.exp(p["a"] + p["b"] * x + p["s"] * e) * scale))


def yhat(x, p):
    return np.exp(p["a"] + p["b"] * x)


def one_rep(rng, p, rep):
    xc, ec = rng.uniform(0, 1, p["n_cal"]), rng.standard_normal(p["n_cal"])
    yc = days(xc, ec, p)
    t = rng.uniform(0, p["window_days"], p["n_cal"])
    keep = t + yc < p["window_days"]
    rand = np.zeros(p["n_cal"], bool)
    rand[rng.choice(p["n_cal"], int(keep.sum()), replace=False)] = True
    xe, ee = rng.uniform(0, 1, p["n_eval"]), rng.standard_normal(p["n_eval"])
    pe = yhat(xe, p)
    shifts = {SCEN[0]: M.shift(yc, yhat(xc, p), p["q"]),
              SCEN[1]: M.shift(yc[keep], yhat(xc[keep], p), p["q"]),
              SCEN[2]: M.shift(yc[rand], yhat(xc[rand], p), p["q"])}
    shifts[SCEN[3]] = shifts[SCEN[4]] = shifts[SCEN[0]]
    ncal = {SCEN[0]: p["n_cal"], SCEN[1]: int(keep.sum()), SCEN[2]: int(rand.sum()), SCEN[3]: p["n_cal"], SCEN[4]: p["n_cal"]}
    scale = {SCEN[0]: 1.0, SCEN[1]: 1.0, SCEN[2]: 1.0, SCEN[3]: p["slower"], SCEN[4]: p["faster"]}
    rows = []
    for s in SCEN:
        ye = days(xe, ee, p, scale[s])
        d = M.promise(pe, shifts[s])
        sc = M.policy_score(ye, d)
        rows.append({"rep": rep, "scenario": s, "cal_n_used": ncal[s], "shift_days": shifts[s],
                     "mean_promised_days": sc["mean_promised_days"], "coverage": sc["coverage"],
                     "n_uncovered": sc["n_missed"], "n_eval": sc["orders"]})
    return rows


def summarise(reps: pd.DataFrame, R: int, q: float):
    def agg(g, col):
        v = g[col]
        return {f"{col}_mean": v.mean(), f"{col}_mc_se": v.std(ddof=1) / np.sqrt(R),
                f"{col}_p05": v.quantile(0.05), f"{col}_p95": v.quantile(0.95)}
    summ = pd.DataFrame([{"scenario": s, **agg(g, "coverage"), **agg(g, "mean_promised_days"), **agg(g, "shift_days"),
                          "cal_n_used_mean": g.cal_n_used.mean(), "share_reps_below_target": (g.coverage < q).mean()}
                         for s, g in reps.groupby("scenario", sort=False)])
    base = reps[reps.scenario == SCEN[0]].set_index("rep")
    diffs = []
    for s in SCEN[1:]:
        g = reps[reps.scenario == s].set_index("rep")
        d = pd.DataFrame({"coverage_pts": (g.coverage - base.coverage) * 100,
                          "mean_promised_days": g.mean_promised_days - base.mean_promised_days,
                          "shift_days": g.shift_days - base.shift_days})
        row = {"scenario_minus_S1": s}
        for col in d:
            row.update({f"d_{col}_mean": d[col].mean(), f"d_{col}_mc_se": d[col].std(ddof=1) / np.sqrt(R),
                        f"d_{col}_p05": d[col].quantile(0.05), f"d_{col}_p95": d[col].quantile(0.95)})
        diffs.append(row)
    return summ, pd.DataFrame(diffs)


def run(p=PARAMS):
    rng = np.random.default_rng(p["seed"])
    reps = pd.DataFrame([r for i in range(p["reps"]) for r in one_rep(rng, p, i)])
    return (reps, *summarise(reps, p["reps"], p["q"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="outputs/e1/sim_paired")
    out = Path(ap.parse_args().out); out.mkdir(parents=True, exist_ok=True)
    reps, summ, diffs = run()
    reps.to_csv(out / "replications.csv", index=False)
    summ.to_csv(out / "summary.csv", index=False)
    diffs.to_csv(out / "paired_differences_vs_S1.csv", index=False)
    (out / "params.json").write_text(json.dumps(PARAMS, indent=2))
    src = Path(__file__).read_bytes()
    (out / "generator_e1_calibration_sim_paired.py").write_bytes(src)
    man = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(out.iterdir()) if f.name != "MANIFEST.sha256"}
    (out / "MANIFEST.sha256").write_text("".join(f"{h}  {n}\n" for n, h in man.items()))
    pd.set_option("display.width", 250)
    print(summ.round(4).to_string(index=False)); print(diffs.round(4).to_string(index=False))
