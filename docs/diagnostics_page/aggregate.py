"""Aggregates for the Olist delivery diagnostics page, from saved repository files only (stdlib; read-only).

Usage: python3 -I aggregate.py <repo root> <out dir>
Writes one JSON file of row objects per dataset and prints checks against the repository's own saved metrics.
"""
import bisect
import csv
import gzip
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

R, OUT = Path(sys.argv[1]), Path(sys.argv[2])
OUT.mkdir(parents=True, exist_ok=True)
MODELS = {"p_logistic": "logistic", "p_gbm": "gbm"}
Z = 1.959963984540054


def write(name, rows):
    (OUT / f"{name}.json").write_text(json.dumps(rows, indent=1))
    print(f"wrote {name}.json: {len(rows)} rows")


def read_csv(rel):
    return list(csv.DictReader(open(R / rel)))


def total(xs):
    """Left-to-right float sum. Python 3.12 made sum() of floats compensated, so sum() would tie the output bits to
    the interpreter version; this keeps the data files identical under any Python 3."""
    s = 0.0
    for x in xs:
        s += x
    return s


def wilson(k, n):
    if n == 0:
        return None, None
    p = k / n
    d = 1 + Z * Z / n
    c = (p + Z * Z / (2 * n)) / d
    h = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


e1 = {r["order_id"]: r for r in csv.DictReader(gzip.open(R / "outputs/e1/score/e_promises_per_order.csv.gz", "rt"))}
SOURCES = {"frozen": read_csv("outputs/stage3/test_predictions.csv"), "refit": read_csv("outputs/stage5/fold_predictions.csv")}
assert {r["order_id"] for r in SOURCES["frozen"]} == set(e1), "stage-3 test set differs from E1's E"
for rows in SOURCES.values():
    for r in rows:
        r["month"] = e1[r["order_id"]]["purchase_month"]
        r["y"] = int(r["y"])
        for col in MODELS:
            r[col] = float(r[col])
for r in SOURCES["refit"]:     # each fold scores the purchase month after its cut-off
    assert r["month"] == r["cutoff"][:7], (r["cutoff"], r["month"])


def groups(rows):
    g = defaultdict(list)
    for r in rows:
        g[r["month"]].append(r)
        g["all"].append(r)
    return g


# Each version is picked by its own stage's rule: stage 3 ranks each purchase week of the whole test period,
# stage 5 each purchase week within its fold. A week that spans two months is never re-ranked across folds.
BUDGET_GROUP = {"frozen": lambda r: r["purchase_week"], "refit": lambda r: (r["cutoff"], r["purchase_week"])}


def budget_curve(src, rows, col):
    """{(month, share %): [selected, late among them, random expected late]} for 1-30% and month 'all'. The picks are
    made once per budget group (the floor(share x n) highest scores, ties by row order, as modeling.top_share_by_week)
    and then counted by purchase month. The random baseline uses the same budgets: a group of n orders with L late
    and k picks adds k * L / n expected late orders."""
    by_group = defaultdict(list)
    for r in rows:
        by_group[BUDGET_GROUP[src](r)].append(r)
    ranked = [(sorted(g, key=lambda r: -r[col]), Counter(r["month"] for r in g if r["y"])) for g in by_group.values()]
    out = defaultdict(lambda: [0, 0, 0.0])
    for pct in range(1, 31):
        for g, late_by_month in ranked:
            n = len(g)
            k = math.floor(pct / 100 * n)
            for r in g[:k]:
                for m in (r["month"], "all"):
                    out[m, pct][0] += 1
                    out[m, pct][1] += r["y"]
            for m, late in late_by_month.items():
                out[m, pct][2] += k * late / n
            out["all", pct][2] += k * sum(late_by_month.values()) / n
    return out


budget, monthly, bins_rows = [], [], []
for src, rows in SOURCES.items():
    curves = {col: budget_curve(src, rows, col) for col in MODELS}
    for month, g in groups(rows).items():
        n, late = len(g), sum(r["y"] for r in g)
        y = [r["y"] for r in g]
        for col, model in MODELS.items():
            for pct in range(1, 31):
                sel, tp, rnd = curves[col][month, pct]
                budget.append({"key": f"{src}|{model}|{month}|{pct}", "source": src, "model": model, "month": month, "share_pct": pct, "orders": n,
                               "late_total": late, "selected": sel, "late_in_selected": tp,
                               "recall": tp / late, "precision": tp / sel if sel else None,
                               "random_expected_late": rnd, "random_expected_recall": rnd / late,
                               "lift_vs_random": tp / rnd if rnd else None})
            p = [r[col] for r in g]
            mp = total(p) / n
            brier = total((a - b) ** 2 for a, b in zip(p, y)) / n
            pc = [min(max(a, 1e-6), 1 - 1e-6) for a in p]
            ll = -total(b * math.log(a) + (1 - b) * math.log(1 - a) for a, b in zip(pc, y)) / n
            lo, hi = wilson(late, n)
            monthly.append({"key": f"{src}|{model}|{month}", "source": src, "model": model, "month": month, "orders": n, "late": late,
                            "observed_rate": late / n, "observed_lo": lo, "observed_hi": hi,
                            "mean_predicted": mp, "observed_to_expected": (late / n) / mp,
                            "brier": brier, "log_loss": ll})
            # equal-count bins on the rank (pd.qcut(p.rank(method="first"), B)), as modeling.calibration_table
            B = 10 if month == "all" else 5
            order = sorted(range(n), key=lambda i: p[i])         # stable: ties ranked by row order
            rank = [0] * n
            for k, i in enumerate(order):
                rank[i] = k + 1
            edges = [1 + (n - 1) * j / B for j in range(B + 1)]
            acc = defaultdict(lambda: [0, 0, 0.0])
            for i in range(n):
                a = acc[max(0, bisect.bisect_left(edges, rank[i]) - 1)]
                a[0] += 1; a[1] += y[i]; a[2] += p[i]
            for b in sorted(acc):
                cnt, k_late, s = acc[b]
                lo, hi = wilson(k_late, cnt)
                bins_rows.append({"key": f"{src}|{model}|{month}|{b + 1}", "source": src, "model": model, "month": month, "bins": B, "bin": b + 1, "orders": cnt,
                                  "late": k_late, "mean_predicted": s / cnt, "observed_rate": k_late / cnt,
                                  "observed_lo": lo, "observed_hi": hi})
write("risk_budget", budget)
write("prob_monthly", monthly)
write("prob_bins", bins_rows)

# E1 promised dates: copied from the saved E1 outputs, not recomputed
pt = {r["policy"]: r for r in read_csv("outputs/e1/score/policy_table.csv")}
pick = [("B1c@0.90 (shifted)", "B1c", "State rule, calibrated", "registered"),
        ("Cstar@0.90 (shifted)", "C*", "Linear quantile regression", "registered"),
        ("Dstar@0.90 (shifted)", "D*", "Shallow gradient boosting (HGB)", "registered"),
        ("replacement reference: stage-7 B0 (F + C, no shift)", "B0", "Retained state rule", "reference"),
        ("Olist promise", "Olist", "Olist's estimated date", "reference")]
write("e1_policies", [{"key": code, "code": code, "label": label, "kind": kind, "q": float(pt[key]["q"]), "orders": int(pt[key]["orders"]),
                       "coverage": float(pt[key]["coverage"]), "mean_promised_days": float(pt[key]["mean_promised_days"]),
                       "n_missed": int(pt[key]["n_missed"]), "source_policy": key} for key, code, label, kind in pick])

write("e1_curves", [{"model": r["model"], "shift": float(r["shift"]), "coverage": float(r["coverage"]), "mean_days": float(r["mean_days"])}
                    for r in read_csv("outputs/e1/posthoc_m4/diagnostic_curves_E.csv")
                    if 0.80 <= float(r["coverage"]) <= 0.995 and round(float(r["shift"]) * 100) % 5 == 0])    # every 0.05-day step

MODEL_CODE = {"linear C*": "linear", "HGB D*": "hgb", "state rule": "state"}
write("e1_matched", [{"key": f"{r['target']}|{MODEL_CODE[r['model']]}", "model_code": MODEL_CODE[r["model"]], "target": r["target"], "target_coverage": float(r["target_coverage"]), "model": r["model"],
                      "achieved_coverage": float(r["achieved_coverage"]), "shift": float(r["shift"]),
                      "mean_days": float(r["mean_days"])}
                     for r in read_csv("outputs/e1/posthoc_m4/matched_coverage_E.csv")])

CODE = {"Dstar@0.90": "D*", "Cstar@0.90": "C*", "B1c, same rule": "B1c", "B0 retained rule": "B0"}
write("e1_rounding", [{"key": f"{r['rule']}|{CODE[r['policy']]}|{CODE[r['reference']]}", "policy_code": CODE[r["policy"]], "ref_code": CODE[r["reference"]], "rule": r["rule"], "policy": r["policy"], "reference": r["reference"],
                       "day_diff": float(r["day_diff"]), "coverage_diff_pts": float(r["coverage_diff_pts"])}
                      for r in read_csv("outputs/e1/posthoc_m4/rounding_comparisons.csv") if r["rule"] in ("ceil", "floor")])

# checks against the repository's saved metrics
budget_by, monthly_by, bins_by = ({r["key"]: r for r in rows} for rows in (budget, monthly, bins_rows))
ok5 = True
for m in read_csv("outputs/stage5/fold_metrics.csv"):
    if m["model"] == "baseline":
        continue
    month = m["eval_from"][:7]
    b, mo = budget_by[f"refit|{m['model']}|{month}|10"], monthly_by[f"refit|{m['model']}|{month}"]
    same = (b["selected"] == int(m["selected"]) and b["late_in_selected"] == int(m["true_late_in_selected"])
            and abs(mo["brier"] - float(m["brier"])) < 1e-9 and abs(mo["mean_predicted"] - float(m["mean_predicted"])) < 1e-9
            and abs(mo["log_loss"] - float(m["log_loss"])) < 1e-9)
    ok5 &= same
    print("check stage5", month, m["model"], "top10%", b["selected"], b["late_in_selected"], "brier/logloss/mean p match:", same)
ok3 = True
for c in read_csv("outputs/stage3/calibration.csv"):
    mine = bins_by[f"frozen|{c['model']}|all|{int(c['bin']) + 1}"]
    same = mine["orders"] == int(c["n"]) and abs(mine["mean_predicted"] - float(c["mean_predicted"])) < 1e-9 and abs(mine["observed_rate"] - float(c["observed_rate"])) < 1e-9
    ok3 &= same
    if not same:
        print("calibration bin mismatch", c, mine)
for m in read_csv("outputs/stage3/test_metrics.csv"):
    if m["model"] != "baseline":
        b = budget_by[f"frozen|{m['model']}|all|10"]
        same = b["selected"] == int(m["selected"]) and b["late_in_selected"] == int(m["true_late_in_selected"])
        ok3 &= same
        print("check stage3", m["model"], "top10%", b["selected"], b["late_in_selected"], "match:", same)
print("stage-3 calibration bins and top-10% picks reproduced:", ok3)
# every share: the months add up to all months (orders, picks and the random baseline)
okadd = True
for src in SOURCES:
    months = sorted({r["month"] for r in budget if r["source"] == src} - {"all"})
    for model in MODELS.values():
        for pct in range(1, 31):
            a = budget_by[f"{src}|{model}|all|{pct}"]
            parts = [budget_by[f"{src}|{model}|{m}|{pct}"] for m in months]
            okadd &= all(a[f] == sum(p[f] for p in parts) for f in ("orders", "late_total", "selected", "late_in_selected"))
            okadd &= abs(a["random_expected_late"] - total(p["random_expected_late"] for p in parts)) < 1e-9
print("every share: months add up to all months:", okadd)
print("scores overstate the late rate in every source/model/month:", all(m["observed_rate"] < m["mean_predicted"] for m in monthly))
print("ALL CHECKS", "OK" if ok5 and ok3 and okadd else "FAILED")
sys.exit(0 if ok5 and ok3 and okadd else 1)
