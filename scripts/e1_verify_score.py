"""Independent re-computation of the E1 final results from the saved per-order E file and bootstrap draws ONLY
(numpy / pandas; no project code). Also one POST-HOC number that the registered output did not include: a
week-block interval for the q = 0.9126 comparison with Olist (the registered rule passed by a narrow margin).
Usage: python3 scripts/e1_verify_score.py [OUT_DIR]   (default AGENT_REVIEW/verify_output)
Writes OUT_DIR/score_verification.csv and OUT_DIR/e_olist_interval.json and checks them against the saved copies
outputs/e1/score_verification.csv and outputs/e1/posthoc/e_olist_interval.json, which it never writes.
Exits non-zero on any mismatch."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "AGENT_REVIEW/verify_output"); OUT.mkdir(parents=True, exist_ok=True)
S = "outputs/e1/score"
po = pd.read_csv(f"{S}/e_promises_per_order.csv.gz")
res = json.load(open(f"{S}/results.json")); pt = pd.read_csv(f"{S}/policy_table.csv").set_index("policy")
comps = json.load(open(f"{S}/comparisons.json"))
y = po.actual_days.to_numpy()
rows = []
close = lambda a, b, tol: bool(np.all(np.abs(np.asarray(a, float) - np.asarray(b, float)) <= tol))
def chk(name, exp, act, tol=1e-9):
    rows.append({"check": name, "expected": exp, "recomputed": act, "pass": close(exp, act, tol)})
cov = lambda d: float((y <= d).mean()); days = lambda d: float(np.mean(d))
pin = lambda d, q: float(np.mean(np.maximum(q * (y - d), (q - 1) * (y - d))))
col = {"B1@0.90": "B1@0.90|promise", "B1c@0.90 (shifted)": "B1c@0.90|promise", "B2@0.90 (shifted)": "B2@0.90|promise",
       "B3@0.90 (shifted)": "B3@0.90|promise", "Cstar@0.90 (shifted)": "Cstar@0.90|promise", "Dstar@0.90 (shifted)": "Dstar@0.90|promise",
       "B3@0.90 (unshifted)": "B3@0.90|promise_unshifted", "Cstar@0.90 (unshifted)": "Cstar@0.90|promise_unshifted",
       "Dstar@0.90 (unshifted)": "Dstar@0.90|promise_unshifted",
       "replacement reference: stage-7 B0 (F + C, no shift)": "stage7_B0_promise", "R0 regression: stage-7 Q2 calibration A": "stage7_Q2A_promise"}
chk("E orders", 19950, len(y))
for name, c in col.items():
    chk(f"{name}: coverage, mean days, pinball", [pt.loc[name, "coverage"], pt.loc[name, "mean_promised_days"], pt.loc[name, "pinball_int"]],
        [cov(po[c]), days(po[c]), pin(po[c].to_numpy(), 0.90)])
# shifted promise = max(1, ceil(pred + frozen shift - 1e-9))
fr = json.load(open("outputs/e1/freeze/FREEZE.json"))
for k, s in fr["shifts_by_policy_and_q"].items():
    chk(f"{k}: promise == max(1, ceil(pred + frozen shift - 1e-9))", 0,
        int((po[f"{k}|promise"] != np.maximum(1, np.ceil(po[f"{k}|pred"] + s["shift_days"] - 1e-9))).sum()))
# H1: R0 and R3, practical rule
def gap(s, r):
    return days(po[r]) - days(po[s]), cov(po[r]) - cov(po[s])
d0, c0 = gap("stage7_B0_promise", "stage7_Q2A_promise"); d3, c3 = gap("B1c@0.90|promise", "B3@0.90|promise")
chk("H1 change in day gap (R3 - R0)", res["H1"]["change_day_gap"], d3 - d0)
chk("H1 change in coverage gap, pts", res["H1"]["change_cov_gap_pts"], (c3 - c0) * 100)
keep = lambda d, c: d <= -1 + 1e-9 and c >= -0.01 - 1e-12
chk("H1 verdict changed (R0 keep -> R3 keep)", float(res["H1"]["verdict_changed"]), float(keep(d0, c0) != keep(d3, c3)), 0)
# H2
chk("H2 g = 0 (C* identical to B3)", res["H2"]["g"], 1 - pin(po["Cstar@0.90|promise_unshifted"].to_numpy(), .9) / pin(po["B3@0.90|promise_unshifted"].to_numpy(), .9))
# H3 / replacement + intervals from the saved draws
draws = pd.read_csv(f"{S}/bootstrap_draws.csv.gz")
wk = po.purchase_week_index.to_numpy()
def interval(diff, scheme):
    Dm = draws[draws.scheme == scheme].sort_values(["replicate", "position"]).week_index.to_numpy().reshape(-1, 17)
    sums = np.array([diff[wk == w].sum() for w in range(17)]); cnt = np.array([(wk == w).sum() for w in range(17)])
    rep = np.array([sums[d].sum() / cnt[d].sum() for d in Dm])
    return np.percentile(rep, [2.5, 97.5])
ref = {"fair: B1c@0.90": "B1c@0.90|promise", "replacement: stage-7 B0": "stage7_B0_promise"}
for cp in comps:
    a = po[cp["policy"].split(" ")[0] + "|promise"].to_numpy(); b = po[ref[cp["reference"]]].to_numpy()
    nm = f"{cp['policy'][:10]} vs {cp['reference'][:12]}"
    chk(f"{nm}: day diff, coverage diff pts", [cp["day_diff"], cp["coverage_diff_pts"]], [a.mean() - b.mean(), ((y <= a).mean() - (y <= b).mean()) * 100])
    chk(f"{nm}: practical rule", float(cp["practical_rule"]), float(keep(a.mean() - b.mean(), (y <= a).mean() - (y <= b).mean())), 0)
    for sch in ("iid", "moving2"):
        chk(f"{nm}: day-diff interval ({sch})", cp["day_diff_ci95"][sch], interval(a - b, sch), 1e-9)
# M vs Olist: rule recomputed + POST-HOC interval
ol = po.olist_promise.to_numpy()
post = {}
for k in ("B1c@0.9126", "Cstar@0.9126", "Dstar@0.9126"):
    a = po[f"{k}|promise"].to_numpy()
    m = next(x for x in res["M_vs_olist"] if x["policy"] == k)
    chk(f"M {k}: tighter-at-similar-reliability rule", float(m["tighter_at_similar_reliability"]),
        float(keep(a.mean() - ol.mean(), (y <= a).mean() - (y <= ol).mean())), 0)
    post[k] = {"day_diff_vs_olist": float(a.mean() - ol.mean()), "coverage_diff_pts_vs_olist": float(((y <= a).mean() - (y <= ol).mean()) * 100),
               "day_diff_ci95_iid": interval(a - ol, "iid").tolist(),
               "coverage_diff_pts_ci95_iid": interval(((y <= a).astype(float) - (y <= ol)) * 100, "iid").tolist(),
               "note": "post hoc (not in the registered output); same saved week draws; does not change the registered verdict"}
json.dump(post, open(OUT / "e_olist_interval.json", "w"), indent=2)
out = pd.DataFrame(rows); out.to_csv(OUT / "score_verification.csv", index=False)
print(out[["check", "pass"]].to_string(index=False)); print(f"{out['pass'].sum()} / {len(out)} pass")
print(json.dumps(post, indent=1))
old = pd.read_csv("outputs/e1/score_verification.csv")
same_checks = old.check.tolist() == out.check.tolist() and old["pass"].tolist() == out["pass"].tolist()
saved = json.load(open("outputs/e1/posthoc/e_olist_interval.json"))
num = lambda d: np.concatenate([np.ravel(d[k][f]) for k in sorted(d) for f in ("day_diff_vs_olist", "coverage_diff_pts_vs_olist",
                                                                                "day_diff_ci95_iid", "coverage_diff_pts_ci95_iid")])
same_post = saved.keys() == post.keys() and close(num(saved), num(post), 1e-9)
print(f"saved outputs/e1/score_verification.csv has the same checks and results: {same_checks}")
print(f"saved outputs/e1/posthoc/e_olist_interval.json reproduced to within 1e-9: {same_post}")
sys.exit(0 if out["pass"].all() and same_checks and same_post else 1)
