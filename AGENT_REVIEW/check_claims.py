"""Checks every quantitative claim in AGENT_REVIEW/claims.json against the saved evidence files.
numpy / pandas / json only. Run from the package root. Exit 1 on any mismatch."""
import json, sys
import numpy as np, pandas as pd

E = "outputs/e1"
res = json.load(open(f"{E}/score/results.json"))
comps = {(c["policy"].split(" ")[0], c["reference"].split(":")[0]): c for c in json.load(open(f"{E}/score/comparisons.json"))}
pt = pd.read_csv(f"{E}/score/policy_table.csv").set_index("policy")
mon = pd.read_csv(f"{E}/score/monthly.csv")
sel = json.load(open(f"{E}/select/selection.json"))
lin = pd.read_csv(f"{E}/select/linear_ablation.csv").set_index("step")
hgb = pd.read_csv(f"{E}/select/hgb_grid.csv").set_index("step")
fr = json.load(open(f"{E}/freeze/FREEZE.json"))
po = pd.read_csv(f"{E}/score/e_promises_per_order.csv.gz")
ph = json.load(open(f"{E}/posthoc/posthoc_v.json"))
phe = json.load(open(f"{E}/posthoc/e_olist_interval.json"))
sim = pd.read_csv(f"{E}/sim_paired/paired_differences_vs_S1.csv").set_index("scenario_minus_S1")
y = po.actual_days.to_numpy()
pin = lambda d: np.mean(np.maximum(0.9 * (y - d), -0.1 * (y - d)))

def actual(cid):
    if cid == "C01": return [res["evaluation_orders"], res["weeks"]]
    if cid == "C02": return [fr["shifts_by_policy_and_q"]["B2@0.90"]["n"]]
    if cid == "C03": return [sel["linear"]["name"] == "C0", sel["hgb"]["name"] == "D3", sel["hgb"]["setting"]["max_depth"], sel["hgb"]["setting"]["max_iter"]]
    if cid == "C04": return [lin.loc["C0", "v_pinball_int"], lin.loc["C3 alpha=0.0001", "v_pinball_int"],
                             (lin.loc["C0", "v_pinball_int"] - lin.loc["C3 alpha=0.0001", "v_pinball_int"]) / lin.loc["C0", "v_pinball_int"],
                             hgb.loc["D3", "v_pinball_int"], (lin.loc["C0", "v_pinball_int"] - hgb.loc["D3", "v_pinball_int"]) / lin.loc["C0", "v_pinball_int"]]
    if cid == "C05":
        h = pd.read_csv(f"{E}/score/h1_steps.csv").set_index("step")
        return [h.loc["R0", "day_gap"], h.loc["R3", "day_gap"], res["H1"]["change_day_gap"], h.loc["R0", "cov_gap"] * 100, h.loc["R3", "cov_gap"] * 100, res["H1"]["verdict_changed"]]
    if cid == "C06": return [res["H2"]["g"], res["H2"]["no_change_selected"]]
    if cid == "C07":
        c = comps[("Dstar@0.90", "fair")]
        return [c["day_diff"], *c["day_diff_ci95"]["iid"], c["coverage_diff_pts"], c["practical_rule"], c["monthly_reliable"], res["H3"]["status"] == "not supported"]
    if cid == "C08": return [comps[("Cstar@0.90", "replacement")]["day_diff"], comps[("Dstar@0.90", "replacement")]["day_diff"],
                             comps[("Cstar@0.90", "replacement")]["practical_rule"], comps[("Dstar@0.90", "replacement")]["practical_rule"]]
    if cid == "C09":
        m = next(x for x in res["M_vs_olist"] if x["policy"] == "Cstar@0.9126")
        return [m["mean_promised_days"] - m["olist_mean_days"], (m["coverage"] - m["olist_coverage"]) * 100, m["tighter_at_similar_reliability"], *phe["Cstar@0.9126"]["day_diff_ci95_iid"]]
    if cid == "C10":
        cal = ["B1c@0.90 (shifted)", "B2@0.90 (shifted)", "B3@0.90 (shifted)", "Dstar@0.90 (shifted)"]
        mm = mon[mon.policy.isin(cal)]
        return [pt.loc[cal, "coverage"].min(), pt.loc[cal, "coverage"].max(), bool((mm.coverage >= 0.90).all())]
    if cid == "C11":
        g = {}
        for k in ("Cstar@0.90", "Dstar@0.90"):
            p = po[f"{k}|pred"]; s = fr["shifts_by_policy_and_q"][k]["shift_days"]; d = po[f"{k}|promise"]
            g[k] = (p.mean(), s, (d - (p + s)).mean(), d.mean())
        return [g["Dstar@0.90"][i] - g["Cstar@0.90"][i] for i in range(4)]
    if cid == "C12":
        cu, du = po["Cstar@0.90|promise_unshifted"].to_numpy(), po["Dstar@0.90|promise_unshifted"].to_numpy()
        return [(y <= cu).mean() * 100, (y <= du).mean() * 100, pin(cu), pin(du), (pin(cu) - pin(du)) / pin(cu)]
    if cid == "C13": return [fr["shifts_by_policy_and_q"]["B2@0.90"]["shift_days"]]
    if cid == "C14": return [ph["argmin_d_9to1"], ph["q90_inverted_cdf"], ph["policies"]["mean, rounded up"]["coverage"] * 100]
    if cid == "C15": return [*ph["bootstrap"]["C3 alpha=0.0001"]["ci95"], *ph["bootstrap"]["D3"]["ci95"]]
    if cid == "C16": return [sim.loc[i, "d_coverage_pts_mean"] for i in sim.index]
    if cid in ("C20", "C21", "C22", "C23", "C24", "C25", "C26", "C27", "C28", "C29"):
        return r3(cid)
    raise KeyError(cid)


def r3(cid):
    """Review-3 post-hoc claims, recomputed here from the per-order files (not read from posthoc_r3.json)."""
    prom = lambda p, s: np.maximum(1, np.ceil(p + s - 1e-9))
    cp = pd.read_csv(f"{E}/final/c_predictions_per_order.csv.gz")
    if cid == "C20":
        out = []
        for k in ("Dstar@0.90", "Cstar@0.90"):
            p = po[f"{k}|pred"].to_numpy()
            cov, days = zip(*[((y <= prom(p, s)).mean(), prom(p, s).mean()) for s in np.arange(-12, 25, 0.01)])
            cov, days = np.array(cov), np.array(days)
            out += [days[cov >= 0.90 - 1e-12].min(), days[cov >= 0.96175 - 1e-12].min()]
        return out
    sh = lambda k: fr["shifts_by_policy_and_q"][k]["shift_days"]
    g = {k: cp[cp.run == k] for k in ("Dstar@0.90", "Cstar@0.90", "B1c@0.90")}
    if cid == "C21":
        cov = {k: (v.actual_days.to_numpy() <= prom(v.prediction_unrounded.to_numpy(), sh(k))).mean() * 100 for k, v in g.items()}
        dd = {k: prom(v.prediction_unrounded.to_numpy(), sh(k)).mean() for k, v in g.items()}
        return [cov["Dstar@0.90"], cov["Cstar@0.90"], cov["B1c@0.90"], dd["Dstar@0.90"], dd["Cstar@0.90"]]
    if cid == "C22":
        def fl(k):
            v = g[k]; yc, p = v.actual_days.to_numpy(), v.prediction_unrounded.to_numpy(); s = sh(k)
            return np.maximum(1, np.floor(po[f"{k}|pred"].to_numpy() + s + 1e-9)), (yc <= np.maximum(1, np.floor(p + s + 1e-9))).mean() * 100, len(yc)
        dC, _, _ = fl("Cstar@0.90"); dD, covC, n = fl("Dstar@0.90"); b, _, _ = fl("B1c@0.90")
        kn = np.ceil((n + 1) * 0.90) / n * 100
        return [dC.mean(), dD.mean(), dD.mean() - b.mean(), ((y <= dD).mean() - (y <= b).mean()) * 100, covC, bool(covC >= kn - 1e-9)]
    if cid == "C25":
        sub = lambda p, s: np.maximum(1, np.ceil(p + s - 1 - 1e-9))
        cov = {k: (v.actual_days.to_numpy() <= sub(v.prediction_unrounded.to_numpy(), sh(k))).mean() * 100 for k, v in g.items()}
        n = len(g["Dstar@0.90"]); kn = np.ceil((n + 1) * 0.90) / n * 100
        yy, pp = np.full(200, 10.0), np.full(200, 0.5); s = np.sort(yy - pp)[int(np.ceil(201 * 0.9)) - 1]
        y1, p1 = np.ones(100), np.full(100, 0.5); s1 = np.sort(y1 - p1)[int(np.ceil(101 * 0.9)) - 1]
        return [cov["B1c@0.90"], cov["Dstar@0.90"], bool(cov["Dstar@0.90"] < kn), (yy <= sub(pp, s)).mean() * 100, (y1 <= sub(p1, s1)).mean() * 100]
    if cid == "C29":
        ok = True
        for k in ("B1c@0.90", "B2@0.90", "B3@0.90", "Cstar@0.90", "Dstar@0.90"):
            ok &= bool((cp[cp.run == k].prediction_unrounded + sh(k)).min() >= 12.5) and bool((po[f"{k}|pred"] + sh(k)).min() >= 12.5)
        return [ok]
    if cid == "C26":
        out = []
        for col, grid in (("Dstar@0.90|pred", np.round(np.arange(-12, 25, 0.01), 2)), ("B1@0.90|pred", np.arange(-12, 20, 1.0))):
            p = po[col].to_numpy(); best = None
            for s in grid:
                d = prom(p, s); c = (y <= d).mean()
                if c >= 0.90 - 1e-12 and (best is None or d.mean() < best[1]):
                    best = (c, d.mean())
            out += [best[0] * 100, best[1]]
        return out
    if cid == "C27":
        f = pd.read_csv(f"{E}/posthoc_m4/e_sample_flow.csv").set_index("purchase_month")
        months = [m for m in f.index if m != "total"]
        same = all(int(f.loc[m, "single_seller"]) == int((po.purchase_month == m).sum()) for m in months)
        t = f.loc["total"]
        return [t.all_purchases, t.estimated_week_le_2018_07_23, t.final_outcome_A_or_L, t.single_seller,
                f.loc["2018-07", "all_purchases"], f.loc["2018-07", "single_seller"], same and int(t.single_seller) == len(po)]
    if cid == "C28":
        def st(mask):
            yy = y[mask]; d = lambda c: po[c].to_numpy()[mask]; cv = lambda c: (yy <= d(c)).mean()
            return [d("Cstar@0.90|promise").mean() - d("B1c@0.90|promise").mean(), d("Dstar@0.90|promise").mean() - d("B1c@0.90|promise").mean(),
                    cv("Dstar@0.90|promise") - cv("B1c@0.90|promise"), d("Cstar@0.90|promise").mean() - d("stage7_B0_promise").mean(),
                    d("Dstar@0.90|promise").mean() - d("stage7_B0_promise").mean(), d("Cstar@0.9126|promise").mean() - d("olist_promise").mean(),
                    cv("Cstar@0.9126|promise") - cv("olist_promise")]
        full = np.array(st(np.ones(len(po), bool)))
        drop = np.array([st((po.purchase_week_index != w).to_numpy()) for w in sorted(po.purchase_week_index.unique())])
        return [bool((np.sign(drop) == np.sign(full)).all()), drop[:, 5].min(), drop[:, 5].max()]
    if cid == "C23":
        jul, apr = po[po.purchase_month == "2018-07"], po[po.purchase_month == "2018-04"]
        am = po.purchase_month.isin(["2018-04", "2018-05"]).to_numpy()
        cov = lambda c: (y[am] <= po[c].to_numpy()[am]).mean() * 100
        return [len(jul), jul.olist_promise.max(), apr.olist_promise.max(), cov("B1c@0.90|promise"), cov("Cstar@0.90|promise"), cov("Dstar@0.90|promise")]
    if cid == "C24":
        mc = pd.read_csv(f"{E}/prep/monthly_counts.csv"); c = mc[mc.segment == "C"].set_index("purchase_month")
        return [c.loc["2017-11", "late_rate"] * 100, c.loc["2017-11", "used"] / c["used"].sum() * 100]

claims = json.load(open("AGENT_REVIEW/claims.json"))["claims"]
rows = []
for c in claims:
    if c.get("check") != "auto":
        continue
    a = actual(c["id"])
    exp = c["values"]
    ok = len(a) == len(exp) and all((x == e) if isinstance(e, (bool, str)) else abs(float(x) - float(e)) <= c.get("tol", 1e-6) for x, e in zip(a, exp))
    rows.append({"id": c["id"], "claim": c["statement"][:90], "pass": ok, "expected": exp, "actual": [round(float(v), 6) if not isinstance(v, (bool, str)) else v for v in a]})
out = pd.DataFrame(rows)
out.to_csv("AGENT_REVIEW/verify_output/claims_check.csv", index=False)
pd.set_option("display.width", 200); pd.set_option("display.max_colwidth", 90)
print(out[["id", "pass", "claim"]].to_string(index=False))
print(f"{int(out['pass'].sum())} / {len(out)} claims match the evidence")
sys.exit(0 if out["pass"].all() else 1)
