"""Independent check of stage 3 from the raw CSVs and the saved predictions. Imports no project module.

    python -I scripts/verify_stage3.py        (run_all runs it after stage 3 and before stage 4)

What it recomputes, without project code
  - population, labels and the label-known model-selection sample, from raw orders + items;
  - for EVERY model (baseline, logistic, gbm): n, late, AP, ROC AUC, Brier, weekly top-10% selected
    and hits, precision and recall, from test_predictions.csv;
  - identities inside test_metrics.csv: precision = hits/selected, recall = hits/late, prevalence = late/n.
Each recomputed value is compared with test_metrics.csv.

Fail closed: the previous independent_verification.json is removed first. It is written again only
when every comparison matches, and it records the SHA-256 of each file it checked, so stage 4 can
reject evidence that belongs to another run. On any mismatch VERIFY_FAILED.json lists them; exit 1.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
MODELS = ("baseline", "logistic", "gbm")
TOL = 1e-9


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def manual_ap(y: np.ndarray, s: np.ndarray) -> float:
    """Average precision as the mean of precision at each positive, with tied scores grouped."""
    idx = np.argsort(-s, kind="stable")
    y, s = y[idx], s[idx]
    ends = np.r_[np.flatnonzero(np.diff(s) != 0), len(y) - 1]
    cum = np.cumsum(y)[ends]
    return float(np.sum(cum / (ends + 1) * np.diff(np.r_[0, cum])) / y.sum())


def manual_auc(y: np.ndarray, s: np.ndarray) -> float:
    """Mann–Whitney rank statistic with average ranks for ties."""
    rank = pd.Series(s).rank(method="average").to_numpy()
    pos = y.sum()
    return float((rank[y == 1].sum() - pos * (pos + 1) / 2) / (pos * (len(y) - pos)))


def capacity(pred: pd.DataFrame, col: str, seed: int, random_order: bool) -> tuple[int, int]:
    """Per purchase week, take floor(10% x n) highest scores. The constant baseline has no ranking:
    its capacity draw is a seeded random order (same rule as stage 3)."""
    z = pred.iloc[np.random.default_rng(seed).permutation(len(pred))] if random_order else pred
    hits = selected = 0
    for _, g in z.groupby("purchase_week", sort=True):
        k = int(len(g) * 0.1)
        top = g.sort_values(col, ascending=False, kind="stable").head(k)
        selected += k
        hits += int(top.y.sum())
    return selected, hits


def recompute(pred: pd.DataFrame, seed: int) -> dict:
    y = pred.y.to_numpy().astype(int)
    out = {}
    for m in MODELS:
        s = pred[f"p_{m}"].to_numpy()
        sel, hits = capacity(pred, f"p_{m}", seed, random_order=(m == "baseline"))
        out[m] = {"n": int(len(y)), "late": int(y.sum()), "average_precision": manual_ap(y, s),
                  "roc_auc": manual_auc(y, s), "brier": float(np.mean((s - y) ** 2)), "selected": sel,
                  "true_late_in_selected": hits, "precision_at_top": hits / sel if sel else float("nan"),
                  "recall_at_top": hits / y.sum()}
    return out


def compare(independent: dict, metrics: pd.DataFrame) -> list[str]:
    """Every recomputed quantity must equal the published one; published rows must be internally consistent."""
    bad = []
    m = metrics.set_index("model")
    for model in MODELS:
        if model not in m.index:
            bad.append(f"{model}: missing from test_metrics.csv")
            continue
        r = m.loc[model]
        for k, v in independent[model].items():
            if not np.isclose(float(r[k]), float(v), rtol=0, atol=TOL):
                bad.append(f"{model}.{k}: published {r[k]} vs independent {v}")
        ident = {"precision_at_top = hits/selected": (r.precision_at_top, r.true_late_in_selected / r.selected),
                 "recall_at_top = hits/late": (r.recall_at_top, r.true_late_in_selected / r.late),
                 "prevalence = late/n": (r.prevalence, r.late / r.n)}
        for name, (a, b) in ident.items():
            if not np.isclose(float(a), float(b), rtol=0, atol=TOL):
                bad.append(f"{model}: identity {name} fails ({a} vs {b})")
    return bad


def population(root: Path) -> pd.DataFrame:
    raw = root / "data" / "raw"
    o = pd.read_csv(raw / "olist_orders_dataset.csv", parse_dates=[
        "order_purchase_timestamp", "order_estimated_delivery_date", "order_delivered_customer_date"])
    it = pd.read_csv(raw / "olist_order_items_dataset.csv", usecols=["order_id", "seller_id"])
    single = it.groupby("order_id").seller_id.nunique()
    p, e, d = o.order_purchase_timestamp, o.order_estimated_delivery_date, o.order_delivered_customer_date
    week = e.dt.normalize() - pd.to_timedelta(e.dt.weekday, unit="D")
    win = json.loads((root / "outputs/qa/stage1_facts.json").read_text())["cohort_proposal"]["selected"]
    ok = (o.order_status.eq("delivered") & d.notna() & d.ge(p) & e.dt.normalize().ge(p.dt.normalize())
          & week.between(win["first_week"], win["last_week"]) & o.order_id.map(single).eq(1))
    pop = o[ok].copy()
    pop["late"] = (pop.order_delivered_customer_date.dt.normalize()
                   > pop.order_estimated_delivery_date.dt.normalize()).astype(int)
    return pop


def verify(root: Path = ROOT) -> tuple[dict, list[str]]:
    s3, qa = root / "outputs/stage3", root / "outputs/qa"
    cfg = yaml.safe_load((root / "config/model.yaml").read_text())
    seed = cfg["models"]["seed"]
    T1, T2 = pd.Timestamp(cfg["splits"]["dev"]["from"]), pd.Timestamp(cfg["splits"]["test"]["from"])
    bad: list[str] = []

    manifest = pd.read_csv(qa / "source_manifest.csv")
    changed = [r.file for r in manifest.itertuples() if sha(root / "data/raw" / r.file) != r.sha256]
    bad += [f"raw file changed: {f}" for f in changed]

    pop = population(root)
    dev = pop[pop.order_purchase_timestamp.ge(T1) & pop.order_purchase_timestamp.lt(T2)]
    known = dev[dev.order_delivered_customer_date.lt(T2)]
    lineage = json.loads((s3 / "lineage.json").read_text())
    if len(known) != lineage["dev_selection_n"] or int(known.late.sum()) != lineage["dev_selection_late"]:
        bad.append(f"selection sample {len(known)}/{int(known.late.sum())} vs lineage "
                   f"{lineage['dev_selection_n']}/{lineage['dev_selection_late']}")

    test = pop[pop.order_purchase_timestamp.ge(T2)].set_index("order_id")
    pred = pd.read_csv(s3 / "test_predictions.csv")
    if set(pred.order_id) != set(test.index) or len(pred) != len(test):
        bad.append(f"test rows: predictions {len(pred)} vs raw population {len(test)}")
        labels_ok = False
    else:
        labels_ok = pred.y.tolist() == test.loc[pred.order_id, "late"].tolist()
        if not labels_ok:
            bad.append("test labels differ from raw")

    independent = recompute(pred, seed)
    metrics = pd.read_csv(s3 / "test_metrics.csv")
    bad += compare(independent, metrics)

    checks = pd.read_csv(s3 / "stage3_checks.csv")
    if not checks["pass"].astype(bool).all():
        bad.append("stage-3 blocking checks do not all pass")

    files = {"test_predictions": s3 / "test_predictions.csv", "test_metrics": s3 / "test_metrics.csv",
             "stage3_checks": s3 / "stage3_checks.csv", "stage3_lineage": s3 / "lineage.json",
             "model_config": root / "config/model.yaml", "source_manifest": qa / "source_manifest.csv",
             "stage1_facts": qa / "stage1_facts.json"}
    results = {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
               "all_match": not bad,
               "compared": {"models": list(MODELS), "quantities_per_model": list(independent["logistic"].keys()),
                            "identities": ["precision = hits/selected", "recall = hits/late", "prevalence = late/n"]},
               "population": len(pop), "original_dev_n": len(dev), "selection_n": len(known),
               "selection_late": int(known.late.sum()), "selection_late_rate": float(known.late.mean()),
               "unavailable_dev_n": len(dev) - len(known), "unavailable_dev_late": int(dev.late.sum() - known.late.sum()),
               "test_labels_match_raw": bool(labels_ok), "all_raw_hashes_match": not changed,
               "blocking_checks_pass": int(len(checks)), "score_checks": independent,
               "bound_sha256": {k: sha(v) for k, v in files.items()}}
    return results, bad


def main(root: Path = ROOT) -> int:
    s3 = root / "outputs/stage3"
    out, fail = s3 / "independent_verification.json", s3 / "qa" / "VERIFY_FAILED.json"
    for p in (out, fail):
        if p.exists():
            p.unlink()
    try:
        results, bad = verify(root)
    except Exception as e:                       # missing file, schema change, ...: also a failure
        results, bad = {}, [f"verifier error: {type(e).__name__}: {e}"]
    if bad:
        fail.parent.mkdir(parents=True, exist_ok=True)
        fail.write_text(json.dumps({"mismatches": bad}, indent=2) + "\n")
        print("INDEPENDENT VERIFICATION FAILED\n  " + "\n  ".join(bad), file=sys.stderr)
        return 1
    out.write_text(json.dumps(results, indent=2) + "\n")
    print(f"independent verification: all match ({len(MODELS)} models x "
          f"{len(results['compared']['quantities_per_model'])} quantities + identities)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
