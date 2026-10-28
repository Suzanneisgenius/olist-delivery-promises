"""Independent check of risk_budget.json at every share, 1-30%, with the repository's own selection rule.

Usage: PYTHONPATH=src python3 docs/diagnostics_page/check_budget.py <repo root> <data dir>
Needs the repository environment (numpy, pandas). Exit 0 when every row matches, 1 otherwise.

- Picks: modeling.top_share_by_week on the stage-3 test set as a whole (frozen) and on each stage-5 fold (refit),
  as those stages scored them. Refit months are folds, so all months is the sum over folds.
- Frozen months: the same weekly picks, counted by purchase month with pandas (a week can span two months).
- Random baseline: sum over the same budget groups of floor(share x n) x late / n.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from olist_analytics.modeling import top_share_by_week

R, DATA = Path(sys.argv[1]), Path(sys.argv[2])
MODELS = {"p_logistic": "logistic", "p_gbm": "gbm"}
month = pd.read_csv(R / "outputs/e1/score/e_promises_per_order.csv.gz", usecols=["order_id", "purchase_month"]).set_index("order_id").purchase_month
frozen = pd.read_csv(R / "outputs/stage3/test_predictions.csv")
refit = pd.read_csv(R / "outputs/stage5/fold_predictions.csv")
for d in (frozen, refit):
    d["month"] = d.order_id.map(month)
frozen["group"] = frozen.purchase_week
refit["group"] = refit.cutoff + "|" + refit.purchase_week
page = {r["key"]: r for r in json.loads((DATA / "risk_budget.json").read_text())}


def picked(d, col, share):
    """Boolean mask of the weekly picks, per budget group, ties by row order."""
    mask = pd.Series(False, index=d.index)
    for _, g in d.groupby("group", sort=False):
        k = int(np.floor(share * len(g)))
        mask[g.sort_values(col, ascending=False, kind="mergesort").index[:k]] = True
    return mask


def random_late(d, share):
    g = d.groupby("group").agg(n=("y", "size"), late=("y", "sum"))
    return float((np.floor(share * g.n) * g.late / g.n).sum())


bad = checked = 0
for src, d in (("frozen", frozen), ("refit", refit)):
    for col, model in MODELS.items():
        for pct in range(1, 31):
            share = pct / 100
            want = {}
            if src == "refit":
                folds = {m: top_share_by_week(f.y, f[col], f.purchase_week, share) for m, f in d.groupby("month")}
                for m, f in folds.items():
                    want[m] = (f["selected"], f["true_late_in_selected"], random_late(d[d.month == m], share))
            else:
                whole = top_share_by_week(d.y, d[col], d.purchase_week, share)
                mask = picked(d, col, share)
                assert (int(mask.sum()), int(d.y[mask].sum())) == (whole["selected"], whole["true_late_in_selected"])
                g = d.groupby("group").agg(n=("y", "size"))
                k_over_n = d.group.map(np.floor(share * g.n) / g.n)
                for m, f in d.groupby("month"):
                    want[m] = (int(mask[f.index].sum()), int(f.y[mask[f.index]].sum()), float((k_over_n[f.index] * f.y).sum()))
            want["all"] = (sum(w[0] for w in want.values()), sum(w[1] for w in want.values()), random_late(d, share))
            for m, (sel, tp, rnd) in want.items():
                r = page[f"{src}|{model}|{m}|{pct}"]
                checked += 1
                if (r["selected"], r["late_in_selected"]) != (sel, tp) or abs(r["random_expected_late"] - rnd) > 1e-9 \
                        or abs(r["lift_vs_random"] - tp / rnd) > 1e-9:
                    bad += 1
                    print("MISMATCH", r["key"], (r["selected"], r["late_in_selected"], r["random_expected_late"]), (sel, tp, rnd))
print(f"risk_budget.json: {checked} rows checked, {bad} mismatches")
print("BUDGET CHECK", "OK" if bad == 0 and checked == len(page) else "FAILED")
sys.exit(0 if bad == 0 and checked == len(page) else 1)
