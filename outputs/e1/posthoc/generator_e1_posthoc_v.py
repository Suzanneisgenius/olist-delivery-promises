"""Post-hoc, descriptive checks on V only (not pre-registered; they change no selection and touch no C / E data).

1. Linear-loss example: on V delivery days, the d minimising 9 x late days + 1 x slack days equals the empirical
   90% quantile (inverted_cdf); compared with promising the mean or the median.
2. Week-block bootstrap (same draws for both, pooled per order, 2,000 reps) of the relative V-loss improvement over
   C0 for the C3 alpha pick and for D3, from the saved per-order predictions of the reproduction run.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

from olist_analytics import e1_data as D, e1_models as M

OUT = Path("outputs/e1/posthoc"); OUT.mkdir(parents=True, exist_ok=True)
po = pd.read_csv("outputs/e1/select_repro1/v_predictions_per_order.csv.gz")
y = po[po.candidate == "C0"].set_index("order_id").actual_days
Y = y.to_numpy()
ds = np.arange(1, 61)
EL = np.array([np.mean(9 * np.maximum(Y - d, 0) + np.maximum(d - Y, 0)) for d in ds])
res = {"n_orders": int(len(Y)), "mean_days": float(Y.mean()), "median_days": float(np.median(Y)),
       "q90_inverted_cdf": float(np.quantile(Y, 0.9, method="inverted_cdf")), "argmin_d_9to1": int(ds[EL.argmin()]),
       "expected_loss_by_d": {int(d): float(l) for d, l in zip(ds, EL)}, "policies": {}}
for name, d in [("mean, rounded up", int(np.ceil(Y.mean()))), ("median", int(np.median(Y))), ("90% quantile", int(res["q90_inverted_cdf"]))]:
    res["policies"][name] = {"d": d, "coverage": float((Y <= d).mean()), "loss_9to1": float(EL[d - 1]),
                             "mean_late_days_if_late": float((Y - d)[Y > d].mean())}
res["F_at_argmin_minus_1"] = float((Y <= res["argmin_d_9to1"] - 1).mean())
res["F_at_argmin"] = float((Y <= res["argmin_d_9to1"]).mean())

pop, history, steps = D.load()
V = D.segment_rows(pop, D.cfg())["V"]["used"].set_index("order_id")
wk = M.week_index(V.loc[y.index, "order_purchase_timestamp"])
def pl(c):
    g = po[po.candidate == c].set_index("order_id").loc[y.index]
    return M.pinball_per_order(g.actual_days, g.promise_days, 0.9)
base = pl("C0")
draws = M.week_draws(int(wk.max()) + 1, 2000, np.random.default_rng(20261015))
res["bootstrap"] = {"weeks": int(wk.max()) + 1, "replicates": 2000, "seed": 20261015}
for c in ["C3 alpha=0.0001", "D3"]:
    diff = pl(c) - base
    rep = M.bootstrap_pooled({"d": diff, "b": base}, wk, draws)
    rel = -rep["d"] / rep["b"]
    lo, hi = np.percentile(rel, [2.5, 97.5])
    res["bootstrap"][c] = {"rel_improvement_vs_C0": float(-diff.mean() / base.mean()), "ci95": [float(lo), float(hi)],
                           "share_reps_at_least_1pct": float((rel >= 0.01).mean()), "share_reps_above_0": float((rel > 0).mean())}
res["bootstrap"]["formula"] = ("replicate r draws 14 week indices with replacement (same draws for every candidate); "
                               "S_r = all orders of the drawn weeks, a week drawn twice counted twice; "
                               "rel_r = -(sum_{i in S_r} (L_cand,i - L_C0,i)) / (sum_{i in S_r} L_C0,i), "
                               "L = pinball at q = 0.90 on the unshifted integer promise; CI = 2.5th / 97.5th percentiles of rel_r")
(OUT / "posthoc_v.json").write_text(json.dumps(res, indent=2))

# ---- evidence files (reviewer: recompute everything from these)
wk_start = (V.loc[y.index, "order_purchase_timestamp"].dt.normalize()
            - pd.to_timedelta(V.loc[y.index, "order_purchase_timestamp"].dt.weekday, unit="D")).dt.date.astype(str)
keepc = ["C0", "C3 alpha=0.0001", "D3"]
ev = po[po.candidate.isin(keepc)].merge(pd.DataFrame({"order_id": y.index, "purchase_week_start": wk_start.to_numpy(),
                                                      "purchase_week_index": wk}), on="order_id", how="left")
assert ev.purchase_week_index.notna().all() and len(ev) == 3 * len(y)
ev[["order_id", "actual_days", "candidate", "prediction_unrounded", "promise_days", "purchase_week_start",
    "purchase_week_index"]].to_csv(OUT / "v_orders.csv.gz", index=False, compression="gzip")
pd.DataFrame([(r, j, int(w)) for r, row in enumerate(draws) for j, w in enumerate(row)],
             columns=["replicate", "position", "week_index"]).to_csv(OUT / "bootstrap_draws.csv.gz", index=False, compression="gzip")
reps = []
for c in ["C3 alpha=0.0001", "D3"]:
    rep = M.bootstrap_pooled({"diff": pl(c) - base, "base": base}, wk, draws)
    reps.append(pd.DataFrame({"replicate": range(len(draws)), "candidate": c, "mean_diff": rep["diff"],
                              "mean_base_C0": rep["base"], "rel_improvement": -rep["diff"] / rep["base"]}))
pd.concat(reps).to_csv(OUT / "bootstrap_replicates.csv", index=False)
import hashlib
(OUT / "generator_e1_posthoc_v.py").write_bytes(Path(__file__).read_bytes())
man = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(OUT.iterdir()) if f.name != "MANIFEST.sha256"}
(OUT / "MANIFEST.sha256").write_text("".join(f"{h}  {n}\n" for n, h in man.items()))
print(json.dumps({k: v for k, v in res.items() if k != "expected_loss_by_d"}, indent=1))
