"""POST-HOC sensitivity analyses prompted by the third external review (2026-10-21). Descriptive only:
they reuse the saved per-order predictions on C and E, choose no new policy, and change no registered verdict.
Curves on E sweep the shift ON E itself (an oracle view used only to compare models at equal coverage).
Writes outputs/e1/posthoc_r3/."""
import json, hashlib
from pathlib import Path
import numpy as np, pandas as pd

E1 = Path("outputs/e1"); OUT = E1 / "posthoc_r3"; OUT.mkdir(parents=True, exist_ok=True)
po = pd.read_csv(E1 / "score/e_promises_per_order.csv.gz")
cp = pd.read_csv(E1 / "final/c_predictions_per_order.csv.gz")
fr = json.load(open(E1 / "freeze/FREEZE.json"))
y = po.actual_days.to_numpy()
promise = lambda p, s: np.maximum(1, np.ceil(p + s - 1e-9))

def frontier(pred, yy, grid):
    """For each shift: coverage and mean promised days; keep the efficient points (min days for each coverage)."""
    rows = [((yy <= promise(pred, s)).mean(), promise(pred, s).mean(), s) for s in grid]
    df = pd.DataFrame(rows, columns=["coverage", "mean_days", "shift"]).sort_values(["coverage", "mean_days"])
    df = df.groupby("coverage", as_index=False).first()
    df = df[df.mean_days == df.mean_days[::-1].cummin()[::-1]]          # efficient: no point with more coverage and fewer days
    return df

def days_at(fr_, c):
    ok = fr_[fr_.coverage >= c - 1e-12]
    return float(ok.mean_days.min()) if len(ok) else np.nan

res = {"note": "post hoc, descriptive; no registered verdict changes"}
# 1. matched coverage on E (oracle sweep) and on C (registered shifts)
cur = {"linear C*": frontier(po["Cstar@0.90|pred"].to_numpy(), y, np.arange(-12, 25, 0.01)),
       "HGB D*": frontier(po["Dstar@0.90|pred"].to_numpy(), y, np.arange(-12, 25, 0.01)),
       "state rule": frontier(po["B1@0.90|pred"].to_numpy(), y, np.arange(-12, 20, 1.0))}
pd.concat([d.assign(model=k) for k, d in cur.items()]).to_csv(OUT / "days_coverage_curves_E.csv", index=False)
levels = {"90% target": 0.90, "B0 coverage 93.95%": 0.93945, "C* registered 96.18%": 0.96175, "D* registered 97.10%": 0.97095}
res["matched_coverage_E"] = {lab: {k: days_at(d, c) for k, d in cur.items()} for lab, c in levels.items()}
onC = {}
for k in ("Cstar@0.90", "Dstar@0.90", "B1c@0.90"):
    g = cp[cp.run == k]; s = fr["shifts_by_policy_and_q"][k]["shift_days"]; d = promise(g.prediction_unrounded.to_numpy(), s)
    onC[k] = {"coverage_C": float((g.actual_days.to_numpy() <= d).mean()), "mean_days_C": float(d.mean())}
res["registered_on_C"] = onC
# 2. integer-aware shift: smallest shift whose ROUNDED promise reaches the k-th order statistic
int_aware = {}
for k in ("B1c@0.90", "B2@0.90", "B3@0.90", "Cstar@0.90", "Dstar@0.90"):
    g = cp[cp.run == k]; p = g.prediction_unrounded.to_numpy(); yc = g.actual_days.to_numpy()
    n = len(yc); kk = int(np.ceil((n + 1) * 0.90))
    integer_pred = bool(np.allclose(p, np.round(p)))
    s_old = fr["shifts_by_policy_and_q"][k]["shift_days"]
    s_new = s_old if integer_pred else float(np.sort(yc - 1 - p)[kk - 1])   # continuous: y <= ceil(p+s) <=> y-1-p < s
    dE = promise(po[f"{k}|pred"].to_numpy(), s_new)
    int_aware[k] = {"integer_predictor": integer_pred, "shift_registered": s_old, "shift_integer_aware": s_new,
                    "coverage_C_registered": float((yc <= promise(p, s_old)).mean()), "coverage_C_integer_aware": float((yc <= promise(p, s_new)).mean()),
                    "E_mean_days": float(dE.mean()), "E_coverage": float((y <= dE).mean())}
b = int_aware["B1c@0.90"]
for k in ("Cstar@0.90", "Dstar@0.90"):
    int_aware[k]["E_day_diff_vs_B1c"] = int_aware[k]["E_mean_days"] - b["E_mean_days"]
    int_aware[k]["E_cov_diff_pts_vs_B1c"] = (int_aware[k]["E_coverage"] - b["E_coverage"]) * 100
res["integer_aware_shift"] = int_aware
# 3. E window: selection on Olist's estimated week (stage-3 population, estimated week <= 2018-07-23)
win = po.groupby("purchase_month").agg(orders=("actual_days", "size"), mean_actual_days=("actual_days", "mean"),
                                       olist_promise_mean=("olist_promise", "mean"), olist_promise_max=("olist_promise", "max")).reset_index()
win.to_csv(OUT / "e_window_by_month.csv", index=False)
res["e_window_by_month"] = win.to_dict(orient="records")
am = po.purchase_month.isin(["2018-04", "2018-05"]).to_numpy()
sens = {}
for k, col in [("B1c", "B1c@0.90|promise"), ("C*", "Cstar@0.90|promise"), ("D*", "Dstar@0.90|promise"), ("B0", "stage7_B0_promise")]:
    d = po[col].to_numpy()
    sens[k] = {"apr_may_coverage": float((y[am] <= d[am]).mean()), "apr_may_mean_days": float(d[am].mean()),
               "jun_jul_coverage": float((y[~am] <= d[~am]).mean()), "jun_jul_mean_days": float(d[~am].mean())}
res["apr_may_vs_jun_jul"] = sens
# 4. seasonality of C
mc = pd.read_csv(E1 / "prep/monthly_counts.csv")
res["late_rate_by_month"] = mc[mc.segment.isin(["C", "E"])].to_dict(orient="records")
(OUT / "posthoc_r3.json").write_text(json.dumps(res, indent=2))
(OUT / "generator_e1_posthoc_review3.py").write_bytes(Path(__file__).read_bytes())
man = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(OUT.iterdir()) if f.name != "MANIFEST.sha256"}
(OUT / "MANIFEST.sha256").write_text("".join(f"{h}  {n}\n" for n, h in man.items()))
print(json.dumps({k: v for k, v in res.items() if k not in ("e_window_by_month", "late_rate_by_month")}, indent=1))
