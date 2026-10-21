"""Independent re-computation of the supplementary numbers from the saved files ONLY (numpy / pandas; no project
code imported). Writes outputs/e1/supplementary_verification.csv; exits non-zero on any mismatch."""
import json, sys
import numpy as np, pandas as pd

rows = []
def chk(name, expected, actual, tol=1e-9):
    ok = bool(np.all(np.abs(np.asarray(expected, float) - np.asarray(actual, float)) <= tol))
    rows.append({"check": name, "expected": expected, "recomputed": actual, "pass": ok})

v = pd.read_csv("outputs/e1/posthoc/v_orders.csv.gz")
js = json.load(open("outputs/e1/posthoc/posthoc_v.json"))
c0 = v[v.candidate == "C0"].sort_values("order_id")
Y = c0.actual_days.to_numpy()
srt = np.sort(Y); q90 = srt[int(np.ceil(0.9 * len(srt))) - 1]          # inverted_cdf by hand
chk("V orders", 12045, len(Y))
chk("mean promise (ceil of mean) coverage 65.5%", js["policies"]["mean, rounded up"]["coverage"], (Y <= np.ceil(Y.mean())).mean())
chk("empirical 90% quantile (ceil(n q)-th order statistic)", js["q90_inverted_cdf"], q90)
loss = lambda d: np.mean(9 * np.maximum(Y - d, 0) + np.maximum(d - Y, 0))
chk("9:1 loss at d = 20", js["policies"]["90% quantile"]["loss_9to1"], loss(20))
chk("argmin of 9:1 loss over d = 1..60", js["argmin_d_9to1"], 1 + int(np.argmin([loss(d) for d in range(1, 61)])))
# integer promise = max(1, ceil(prediction - 1e-9))
chk("promise_days == max(1, ceil(pred - 1e-9)) for all rows", 0,
    int((v.promise_days != np.maximum(1, np.ceil(v.prediction_unrounded - 1e-9))).sum()))
pin = lambda y, d: np.maximum(0.9 * (y - d), -0.1 * (y - d))
draws = pd.read_csv("outputs/e1/posthoc/bootstrap_draws.csv.gz").sort_values(["replicate", "position"])
D = draws.week_index.to_numpy().reshape(-1, 14)
base = pin(c0.actual_days.to_numpy(), c0.promise_days.to_numpy())
wk = c0.purchase_week_index.to_numpy().astype(int)
for cand in ["C3 alpha=0.0001", "D3"]:
    cc = v[v.candidate == cand].sort_values("order_id")
    diff = pin(cc.actual_days.to_numpy(), cc.promise_days.to_numpy()) - base
    sd = np.array([diff[wk == w].sum() for w in range(14)]); sb = np.array([base[wk == w].sum() for w in range(14)])
    rel = np.array([-sd[d].sum() / sb[d].sum() for d in D])
    chk(f"{cand}: point relative improvement", js["bootstrap"][cand]["rel_improvement_vs_C0"], -diff.mean() / base.mean())
    chk(f"{cand}: 95% interval from saved draws", js["bootstrap"][cand]["ci95"], np.percentile(rel, [2.5, 97.5]))

for run, path in [("run 1", "outputs/e1/sim"), ("run 2 paired", "outputs/e1/sim_paired")]:
    r = pd.read_csv(f"{path}/replications.csv"); s = pd.read_csv(f"{path}/summary.csv").set_index("scenario")
    for sc, g in r.groupby("scenario"):
        chk(f"sim {run}: {sc[:3]} coverage mean", s.loc[sc, "coverage_mean"], g.coverage.mean(), 1e-12)
        chk(f"sim {run}: {sc[:3]} coverage p05/p95", [s.loc[sc, "coverage_p05"], s.loc[sc, "coverage_p95"]],
            [g.coverage.quantile(0.05), g.coverage.quantile(0.95)], 1e-12)
        chk(f"sim {run}: {sc[:3]} share below 0.90", s.loc[sc, "share_reps_below_target"], (g.coverage < 0.9).mean(), 1e-12)
    if "n_uncovered" in r:
        chk(f"sim {run}: coverage == 1 - n_uncovered / n_eval", 0, float(np.max(np.abs(r.coverage - (1 - r.n_uncovered / r.n_eval)))), 1e-12)
        w = r.pivot(index="rep", columns="scenario", values="shift_days")
        chk(f"sim {run}: S3a/S3b reuse the S1 shift in every replication", 0,
            float(np.max(np.abs(w.filter(like="S3").to_numpy() - w.filter(like="S1").to_numpy()))), 0)
        dd = pd.read_csv(f"{path}/paired_differences_vs_S1.csv").set_index("scenario_minus_S1")
        cov = r.pivot(index="rep", columns="scenario", values="coverage")
        s1 = [c for c in cov if c.startswith("S1")][0]
        for sc in dd.index:
            d = (cov[sc] - cov[s1]) * 100
            chk(f"sim {run}: paired diff {sc[:7]} mean and MC SE", [dd.loc[sc, "d_coverage_pts_mean"], dd.loc[sc, "d_coverage_pts_mc_se"]],
                [d.mean(), d.std(ddof=1) / np.sqrt(len(d))], 1e-10)

out = pd.DataFrame(rows); out.to_csv("outputs/e1/supplementary_verification.csv", index=False)
print(out[["check", "pass"]].to_string(index=False)); print(f"{out['pass'].sum()} / {len(out)} pass")
sys.exit(0 if out["pass"].all() else 1)
