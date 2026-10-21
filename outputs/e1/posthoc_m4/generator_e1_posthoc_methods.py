"""POST-HOC methodological review (fourth review, 2026-10-21). Descriptive only.

Reuses the frozen per-order predictions on C and E; fits nothing, selects no policy, changes no registered verdict.
Writes outputs/e1/posthoc_m4/:
    rounding_rules.csv          ceil (registered) / floor / minus_one on C and E for every shifted q = 0.90 policy
    rounding_comparisons.csv    D*, C* vs B1c and B0 under each rule (point estimates; no interval)
    matched_coverage_E.csv      diagnostic sweep on E: target coverage, ACHIEVED coverage, shift, mean days
    e_sample_flow.csv           how purchases from 2018-04-01 become E, by purchase month
    e_window_comparison.csv     full E vs April-May vs June-July, registered policies and references
    leave_one_week_out.csv      core registered differences with each purchase week removed in turn
    posthoc_m4.json, MANIFEST.sha256, generator copy
"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import e1_rounding_rules as R  # noqa: E402

E1 = Path("outputs/e1"); OUT = E1 / "posthoc_m4"; OUT.mkdir(parents=True, exist_ok=True)
po = pd.read_csv(E1 / "score/e_promises_per_order.csv.gz")
cp = pd.read_csv(E1 / "final/c_predictions_per_order.csv.gz")
fr = json.load(open(E1 / "freeze/FREEZE.json"))
pt = pd.read_csv(E1 / "score/policy_table.csv").set_index("policy")
y = po.actual_days.to_numpy()
res = {"note": "post hoc, descriptive; frozen predictions only; no registered verdict changes"}

# ---------------------------------------------------------------- 1. rounding rules
SHIFTED = ["B1c@0.90", "B2@0.90", "B3@0.90", "Cstar@0.90", "Dstar@0.90"]
rows, prom = [], {}
for key in SHIFTED:
    g = cp[cp.run == key]; yc, pc = g.actual_days.to_numpy(), g.prediction_unrounded.to_numpy()
    s = R.shift(yc, pc, 0.90)
    assert abs(s - fr["shifts_by_policy_and_q"][key]["shift_days"]) < 1e-9, key           # = frozen shift
    pe = po[f"{key}|pred"].to_numpy()
    assert np.array_equal(R.promise(pe, s, "ceil"), po[f"{key}|promise"].to_numpy()), key   # = registered promise
    n, k = len(yc), int(np.ceil((len(yc) + 1) * 0.90))
    for rule in R.RULES:
        dc, de = R.promise(pc, s, rule), R.promise(pe, s, rule)
        prom[(key, rule)] = de
        rows.append({"policy": key, "rule": rule, "shift": s, "k": k, "n_C": n, "k_over_n": k / n,
                     "coverage_C": (yc <= dc).mean(), "share_C_with_Y_le_U": (yc <= pc + s + R.TOL).mean(),
                     "mean_days_C": dc.mean(), "coverage_E": (y <= de).mean(), "mean_days_E": de.mean(),
                     "U_on_whole_number_C": int(R.on_integer_boundary(pc, s).sum()),
                     "U_on_whole_number_E": int(R.on_integer_boundary(pe, s).sum()),
                     "registered_rounding_slack_E": float((R.promise(pe, s, "ceil") - (pe + s)).mean())})  # arithmetic part of the registered promise
rr = pd.DataFrame(rows); rr.to_csv(OUT / "rounding_rules.csv", index=False)
res["rounding_rules"] = rr.to_dict(orient="records")

b0 = po["stage7_B0_promise"].to_numpy()
cmp_rows = []
for rule in R.RULES:
    for pol in ("Dstar@0.90", "Cstar@0.90"):
        d = prom[(pol, rule)]
        for ref_name, ref in (("B1c, same rule", prom[("B1c@0.90", rule)]), ("B0 retained rule", b0)):
            cmp_rows.append({"rule": rule, "policy": pol, "reference": ref_name, "day_diff": d.mean() - ref.mean(),
                             "coverage_diff_pts": ((y <= d).mean() - (y <= ref).mean()) * 100})
rc = pd.DataFrame(cmp_rows); rc.to_csv(OUT / "rounding_comparisons.csv", index=False)
res["rounding_comparisons"] = rc.to_dict(orient="records")

# the earlier post-hoc "integer-aware shift" (outputs/e1/posthoc_r3) is the minus_one rule; its counterexample:
yy, pp = np.full(200, 10.0), np.full(200, 0.5)
s_old = float(np.sort(yy - 1 - pp)[int(np.ceil(201 * 0.9)) - 1])
res["counterexample_constant_10_days"] = {
    "posthoc_r3_rule_coverage": float((yy <= np.maximum(1, np.ceil(pp + s_old - 1e-9))).mean()),
    "floor_coverage": float((yy <= R.promise(pp, R.shift(yy, pp, 0.9), "floor")).mean()),
    "ceil_coverage": float((yy <= R.promise(pp, R.shift(yy, pp, 0.9), "ceil")).mean())}

# ---------------------------------------------------------------- 2. diagnostic sweep on E with achieved coverage
def sweep(pred, grid):
    out = []
    for s in grid:
        d = np.maximum(1, np.ceil(pred + s - 1e-9))
        out.append(((y <= d).mean(), d.mean(), s))
    return pd.DataFrame(out, columns=["coverage", "mean_days", "shift"])

curves = {"linear C*": sweep(po["Cstar@0.90|pred"].to_numpy(), np.round(np.arange(-12, 25, 0.01), 2)),
          "HGB D*": sweep(po["Dstar@0.90|pred"].to_numpy(), np.round(np.arange(-12, 25, 0.01), 2)),
          "state rule": sweep(po["B1@0.90|pred"].to_numpy(), np.arange(-12, 20, 1.0))}
targets = {"90% target": 0.90, "B0 coverage": float((y <= b0).mean()),
           "C* registered coverage": float(pt.loc["Cstar@0.90 (shifted)", "coverage"]),
           "D* registered coverage": float(pt.loc["Dstar@0.90 (shifted)", "coverage"])}
mrows = []
for lab, t in targets.items():
    for model, cv in curves.items():
        ok = cv[cv.coverage >= t - 1e-12]
        best = ok.loc[ok.mean_days.idxmin()]               # fewest days among sweep points reaching the target
        mrows.append({"target": lab, "target_coverage": t, "model": model, "achieved_coverage": best.coverage,
                      "shift": best["shift"], "mean_days": best.mean_days})
mc = pd.DataFrame(mrows); mc.to_csv(OUT / "matched_coverage_E.csv", index=False)
res["matched_coverage_E"] = mc.to_dict(orient="records")
pd.concat([c.assign(model=k) for k, c in curves.items()]).to_csv(OUT / "diagnostic_curves_E.csv", index=False)

# ---------------------------------------------------------------- 3. E sample flow by purchase month
mart = pd.read_csv("outputs/marts/orders_mart.csv", usecols=["order_id", "order_purchase_timestamp", "estimated_week",
                                                            "outcome_bucket", "n_sellers"], parse_dates=["order_purchase_timestamp", "estimated_week"])
LAST_WEEK = pd.Timestamp("2018-07-23"); FIRST_WEEK = pd.Timestamp("2017-02-27")      # config/approvals.yaml comparison_window
m = mart[mart.order_purchase_timestamp >= "2018-04-01"].copy()
m["purchase_month"] = m.order_purchase_timestamp.dt.to_period("M").astype(str)
s1 = m.estimated_week.between(FIRST_WEEK, LAST_WEEK)
s2 = s1 & m.outcome_bucket.isin(["A", "L"])
s3 = s2 & (m.n_sellers == 1)
flow = (pd.DataFrame({"purchase_month": m.purchase_month, "all_purchases": 1, "estimated_week_le_2018_07_23": s1,
                      "final_outcome_A_or_L": s2, "single_seller": s3})
        .groupby("purchase_month").sum().reset_index())
flow["E_orders"] = flow.purchase_month.map(po.groupby("purchase_month").size()).fillna(0).astype(int)
assert (flow.single_seller == flow.E_orders).all(), flow                               # reproduces E exactly
tot = flow.drop(columns="purchase_month").sum(); tot["purchase_month"] = "total"
flow = pd.concat([flow, tot.to_frame().T], ignore_index=True)
flow.to_csv(OUT / "e_sample_flow.csv", index=False)
res["e_sample_flow"] = flow.to_dict(orient="records")

# ---------------------------------------------------------------- 4. full E vs April-May vs June-July
cols = {"B0 retained rule": "stage7_B0_promise", "Olist promise": "olist_promise", "B1c state rule": "B1c@0.90|promise",
        "C* linear": "Cstar@0.90|promise", "D* HGB": "Dstar@0.90|promise"}
am = po.purchase_month.isin(["2018-04", "2018-05"]).to_numpy()
wrows = []
for name, c in cols.items():
    d = po[c].to_numpy()
    for lab, mask in (("full E", np.ones_like(am)), ("April-May", am), ("June-July", ~am)):
        wrows.append({"policy": name, "window": lab, "orders": int(mask.sum()), "coverage": (y[mask] <= d[mask]).mean(),
                      "mean_days": d[mask].mean()})
wc = pd.DataFrame(wrows); wc.to_csv(OUT / "e_window_comparison.csv", index=False)
res["e_window_comparison"] = wc.to_dict(orient="records")

# ---------------------------------------------------------------- 5. leave one purchase week out
def stats(mask):
    yy = y[mask]; d = lambda c: po[c].to_numpy()[mask]
    out = {}
    out["H1 R3 day gap (C* - B1c)"] = d("Cstar@0.90|promise").mean() - d("B1c@0.90|promise").mean()
    out["H3 D* - B1c days"] = d("Dstar@0.90|promise").mean() - d("B1c@0.90|promise").mean()
    out["H3 D* - B1c coverage pts"] = ((yy <= d("Dstar@0.90|promise")).mean() - (yy <= d("B1c@0.90|promise")).mean()) * 100
    out["C* - B0 days"] = d("Cstar@0.90|promise").mean() - d("stage7_B0_promise").mean()
    out["D* - B0 days"] = d("Dstar@0.90|promise").mean() - d("stage7_B0_promise").mean()
    out["C*@0.9126 - Olist days"] = d("Cstar@0.9126|promise").mean() - d("olist_promise").mean()
    out["C*@0.9126 - Olist coverage pts"] = ((yy <= d("Cstar@0.9126|promise")).mean() - (yy <= d("olist_promise")).mean()) * 100
    return out

full = stats(np.ones(len(po), bool))
weeks = sorted(po.purchase_week_index.unique())
lw = pd.DataFrame([{"week_removed": w, "orders_removed": int((po.purchase_week_index == w).sum()),
                    **stats((po.purchase_week_index != w).to_numpy())} for w in weeks])
lw.to_csv(OUT / "leave_one_week_out.csv", index=False)
summ = []
for c in full:
    summ.append({"statistic": c, "full_E": full[c], "min_drop_one": lw[c].min(), "max_drop_one": lw[c].max(),
                 "week_at_min": int(lw.loc[lw[c].idxmin(), "week_removed"]), "week_at_max": int(lw.loc[lw[c].idxmax(), "week_removed"]),
                 "sign_constant": bool((np.sign(lw[c]) == np.sign(full[c])).all())})
res["leave_one_week_out"] = summ

(OUT / "posthoc_m4.json").write_text(json.dumps(res, indent=2, default=float))
(OUT / "generator_e1_posthoc_methods.py").write_bytes(Path(__file__).read_bytes())
(OUT / "generator_e1_rounding_rules.py").write_bytes((Path(__file__).parent / "e1_rounding_rules.py").read_bytes())
man = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(OUT.iterdir()) if f.name != "MANIFEST.sha256"}
(OUT / "MANIFEST.sha256").write_text("".join(f"{h}  {n}\n" for n, h in man.items()))

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(rr[["policy", "rule", "shift", "coverage_C", "share_C_with_Y_le_U", "k_over_n", "mean_days_E", "coverage_E",
          "U_on_whole_number_C", "U_on_whole_number_E", "registered_rounding_slack_E"]].round(4).to_string(index=False))
print(rc.round(3).to_string(index=False))
print(res["counterexample_constant_10_days"])
print(mc.round(4).to_string(index=False))
print(flow.to_string(index=False))
print(wc.round(4).to_string(index=False))
print(pd.DataFrame(summ).round(3).to_string(index=False))
