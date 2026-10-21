"""E1 data layer: segments, seller-history snapshots (U / O) and sample tables.

Reuses the stage-3 population and the stage-3 snapshot code unchanged (`features.py`); nothing here edits stage 7.
Information rule: a row is scored at its purchase time; seller history comes from a snapshot at time T where only
orders DELIVERED before T contribute labels (enforced inside `features.seller_snapshot`).
"""
from __future__ import annotations

import json

import pandas as pd

from .date_policy import required_days
from .features import CFG as CFG3, attach_seller, model_population, month_start, order_features
from .io import ROOT, load_yaml

SEGMENTS = ("F0", "V", "F", "C", "E")


def cfg() -> dict:
    return load_yaml("date_model_e1.yaml")


def load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """(population, seller history, exclusion steps)."""
    from .run_stage3 import load_mart
    mart = load_mart()
    sel = json.loads((ROOT / "outputs" / "qa" / "stage1_facts.json").read_text())["cohort_proposal"]["selected"]
    pop, steps = model_population(mart, sel["first_week"], sel["last_week"])
    history = mart[(mart.n_sellers == 1) & mart.single_seller_id.notna()]
    return pop, history, steps


def _window(pop: pd.DataFrame, seg: dict) -> pd.Series:
    P = pop.order_purchase_timestamp
    m = pd.Series(True, index=pop.index)
    if seg["from"]:
        m &= P >= pd.Timestamp(seg["from"])
    if seg["to"]:
        m &= P < pd.Timestamp(seg["to"])
    return m


def segment_rows(pop: pd.DataFrame, c: dict) -> dict[str, dict[str, pd.DataFrame]]:
    """{name: {"eligible": rows in the purchase window, "used": eligible rows with a label known at the cutoff}}."""
    out = {}
    for name in SEGMENTS:
        seg = c["segments"][name]
        el = pop[_window(pop, seg)]
        cut = seg["label_cutoff"]
        used = el[el.order_delivered_customer_date < pd.Timestamp(cut)] if cut else el
        out[name] = {"eligible": el, "used": used}
    return out


def snapshot_times(rows: pd.DataFrame, segment: str, rule: str) -> pd.Series:
    """When each row's seller history is taken. U: purchase-month start everywhere. O: stage-7 scheme."""
    if rule == "U":
        return month_start(rows.order_purchase_timestamp)
    if rule == "O":
        fixed = {"C": "2017-10-01", "E": "2018-04-01"}
        if segment == "F":
            return month_start(rows.order_purchase_timestamp)
        if segment in fixed:
            return pd.Series(pd.Timestamp(fixed[segment]), index=rows.index)
        raise ValueError(f"O snapshot is defined only for F, C, E (got {segment})")
    raise ValueError(rule)


def features(rows: pd.DataFrame, history: pd.DataFrame, segment: str, rule: str) -> tuple[pd.DataFrame, list[dict]]:
    """Checkout-time fields + seller history at the row's snapshot time (raises on any future label)."""
    base = order_features(rows)
    return attach_seller(rows, base, history, snapshot_times(rows, segment, rule), CFG3["seller_history"]["smoothing_k"])


def labels(rows: pd.DataFrame) -> pd.Series:
    return required_days(rows)


# ------------------------------------------------------------------ sample tables and checks
def sample_tables(pop: pd.DataFrame, segs: dict, steps: pd.DataFrame, c: dict) -> dict[str, pd.DataFrame]:
    counts = []
    for name, s in segs.items():
        u = s["used"]
        cut = c["segments"][name]["label_cutoff"]
        counts.append({"segment": name, "purchases_from": c["segments"][name]["from"], "purchases_to": c["segments"][name]["to"],
                       "label_cutoff": cut, "eligible": len(s["eligible"]), "used": len(u),
                       "share_used": len(u) / len(s["eligible"]) if len(s["eligible"]) else float("nan"),
                       "late_rate_used": float(u.is_late.mean()), "late_rate_eligible": float(s["eligible"].is_late.mean()),
                       "first_purchase": str(u.order_purchase_timestamp.min()), "last_purchase": str(u.order_purchase_timestamp.max())})
    monthly = []
    for name, s in segs.items():
        u = s["used"]
        for mth, g in u.groupby(u.order_purchase_timestamp.dt.to_period("M")):
            monthly.append({"segment": name, "purchase_month": str(mth), "used": len(g), "late_rate": float(g.is_late.mean())})
    return {"segment_counts": pd.DataFrame(counts), "monthly_counts": pd.DataFrame(monthly), "exclusion_steps": steps.copy()}


def id_sha256(order_ids) -> str:
    """SHA-256 of the sorted order ids, one per line (identifies a sample list exactly)."""
    import hashlib
    return hashlib.sha256("\n".join(sorted(map(str, order_ids))).encode()).hexdigest()


def partition_manifest(segs: dict, c: dict) -> pd.DataFrame:
    """One line per partition: eligible / label known / used / excluded with reason / ranges / id hash."""
    rows = []
    for name in SEGMENTS:
        el, u = segs[name]["eligible"], segs[name]["used"]
        cut = c["segments"][name]["label_cutoff"]
        rows.append({"segment": name, "eligible": len(el),
                     "labels_known_before_cutoff": len(u) if cut else len(el), "used": len(u),
                     "excluded": len(el) - len(u),
                     "excluded_reason": f"delivered on/after label cutoff {cut}" if cut else "none (scored, not fitted)",
                     "purchase_min": str(u.order_purchase_timestamp.min()), "purchase_max": str(u.order_purchase_timestamp.max()),
                     "latest_label": str(u.order_delivered_customer_date.max()), "label_cutoff": cut,
                     "id_sha256": id_sha256(u.order_id)})
    return pd.DataFrame(rows)


def partition_checks(segs: dict, c: dict) -> pd.DataFrame:
    """Selection stage: F0 and V disjoint. Final stage: F, C, E pairwise disjoint. F == F0 + V is NOT required."""
    ids = {n: set(segs[n]["used"].order_id) for n in SEGMENTS}
    rows = []
    add = lambda check, expected, actual: rows.append({"check": check, "expected": expected, "actual": actual,
                                                       "pass": str(expected) == str(actual)})
    sel, fin = c["partitions"]["disjoint_selection"], c["partitions"]["disjoint_final"]
    pairs = [(a, b) for i, a in enumerate(sel) for b in sel[i + 1:]] + [(a, b) for i, a in enumerate(fin) for b in fin[i + 1:]]
    for a, b in pairs:
        add(f"{a} and {b} share no order", 0, len(ids[a] & ids[b]))
    add("F0 and V used rows are contained in F (F may hold more)", True, (ids["F0"] | ids["V"]) <= ids["F"])
    for n in SEGMENTS:
        u = segs[n]["used"]
        add(f"{n}: no duplicate order ids", 0, int(u.order_id.duplicated().sum()))
        cut = c["segments"][n]["label_cutoff"]
        if cut:
            add(f"{n}: every used label delivered before {cut}", True,
                bool((u.order_delivered_customer_date < pd.Timestamp(cut)).all()))
    return pd.DataFrame(rows)
