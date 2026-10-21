"""Purchase-time feature frame for the late-delivery model (stage 3).

Information rule
  A row is scored at its purchase time. Order-level features come only from fields
  fixed at checkout. Seller-history features come from a SNAPSHOT taken at time T:
  only single-seller orders whose DELIVERY happened before T contribute a label.
  Filtering history by purchase time alone would leak labels that became known later.

Snapshot times
  training rows   : start of the row's purchase month (as a monthly batch refresh would do)
  evaluation rows : start of the evaluation block, frozen (no labels from inside the block)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .io import load_yaml

CFG = load_yaml("model.yaml")
NUM = CFG["features"]["numeric"]
CAT = CFG["features"]["categorical"]
FEATURES = NUM + CAT
FORBIDDEN = set(CFG["features"]["forbidden"])


class LeakageError(AssertionError):
    pass


def model_population(mart: pd.DataFrame, first_week, last_week) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rows to model plus a reconciliation of every exclusion step."""
    steps = []
    m = mart
    steps.append(("all orders", len(m)))
    m = m[m.estimated_week.between(pd.Timestamp(first_week), pd.Timestamp(last_week))]
    steps.append(("estimated week inside approved window", len(m)))
    m = m[m.outcome_bucket.isin(CFG["population"]["outcome_buckets"])]
    steps.append(("final outcome A or L (U, X excluded)", len(m)))
    if CFG["population"]["single_seller_only"]:
        m = m[m.n_sellers == 1]
        steps.append(("single seller", len(m)))
    return m.copy(), pd.DataFrame(steps, columns=["step", "orders"])


def assign_split(p: pd.Series) -> pd.Series:
    s = CFG["splits"]
    out = pd.Series("test", index=p.index)
    out[p < pd.Timestamp(s["test"]["from"])] = "dev"
    out[p < pd.Timestamp(s["dev"]["from"])] = "train"
    return out


def selection_labels_known_before(rows: pd.DataFrame, cutoff) -> pd.DataFrame:
    """Labels used to choose a model must be known when that model is chosen."""
    cutoff = pd.Timestamp(cutoff)
    return rows[(rows.order_purchase_timestamp < cutoff)
                & (rows.order_delivered_customer_date < cutoff)].copy()


def order_features(m: pd.DataFrame) -> pd.DataFrame:
    """Checkout-time fields only."""
    P = m.order_purchase_timestamp
    f = pd.DataFrame(index=m.index)
    f["estimated_days"] = (m.order_estimated_delivery_date.dt.normalize() - P.dt.normalize()).dt.days
    f["distance_km"] = m.distance_km
    f["items_price_sum"] = m.items_price_sum
    f["items_freight_sum"] = m.items_freight_sum
    f["freight_ratio"] = m.items_freight_sum / m.items_price_sum.where(m.items_price_sum > 0)
    f["weight_g_sum"] = m.weight_g_sum
    f["n_item_lines"] = m.n_item_lines
    f["n_distinct_products"] = m.n_distinct_products
    f["same_state"] = (m.seller_state == m.customer_state_reported).astype(float).where(m.seller_state.notna())
    f["purchase_hour"] = P.dt.hour
    f["purchase_dow"] = P.dt.weekday
    f["customer_state_reported"] = m.customer_state_reported.astype(str)
    f["seller_state"] = m.seller_state.fillna("UNKNOWN").astype(str)
    f["top_price_category"] = m.top_price_category.fillna("UNKNOWN").astype(str)
    return f


def seller_snapshot(history: pd.DataFrame, T: pd.Timestamp, k: float) -> tuple[pd.DataFrame, dict]:
    """Seller statistics knowable at time T. `history` = all single-seller orders (any window)."""
    placed = history[history.order_purchase_timestamp < T]
    known = placed[placed.outcome_bucket.isin(["A", "L"]) & (placed.order_delivered_customer_date < T)]
    if len(known) and known.order_delivered_customer_date.max() >= T:
        raise LeakageError("snapshot contains a label delivered at/after T")
    prior = float(known.is_late.mean()) if len(known) else 0.0
    g = known.groupby("single_seller_id")
    snap = pd.DataFrame({
        "seller_hist_n_delivered": g.size(),
        "seller_hist_late": g.is_late.sum(),
        "seller_hist_handling_median_h": known.handling_hours.where(known.is_stage_eligible).groupby(known.single_seller_id).median(),
    })
    pl = placed.groupby("single_seller_id")
    snap = snap.join(pd.DataFrame({"seller_hist_n_placed": pl.size(),
                                   "seller_first_purchase": pl.order_purchase_timestamp.min()}), how="outer")
    snap["seller_hist_n_delivered"] = snap.seller_hist_n_delivered.fillna(0)
    snap["seller_hist_late"] = snap.seller_hist_late.fillna(0)
    snap["seller_hist_late_rate"] = (snap.seller_hist_late + k * prior) / (snap.seller_hist_n_delivered + k)
    snap["seller_age_days"] = (T - snap.seller_first_purchase).dt.total_seconds() / 86400
    meta = {"T": str(T), "labels_known": int(len(known)), "prior_late_rate": prior,
            "max_label_delivery": str(known.order_delivered_customer_date.max()) if len(known) else None,
            "handling_history_excluded_invalid_stage": int((~known.is_stage_eligible).sum())}
    return snap.drop(columns=["seller_hist_late", "seller_first_purchase"]), meta


def attach_seller(rows: pd.DataFrame, f: pd.DataFrame, history: pd.DataFrame, snapshot_at: pd.Series,
                  k: float) -> tuple[pd.DataFrame, list[dict]]:
    """Join the seller snapshot that applies to each row (one snapshot per distinct time)."""
    cols = ["seller_hist_n_delivered", "seller_hist_late_rate", "seller_hist_n_placed",
            "seller_hist_handling_median_h", "seller_age_days"]
    out = pd.DataFrame(index=rows.index, columns=cols, dtype=float)
    metas = []
    for T, idx in snapshot_at.groupby(snapshot_at).groups.items():
        T = pd.Timestamp(T)
        if (rows.loc[idx, "order_purchase_timestamp"] < T).any():
            raise LeakageError(f"row scored before its snapshot time {T}")
        snap, meta = seller_snapshot(history, T, k)
        j = rows.loc[idx, ["single_seller_id"]].join(snap, on="single_seller_id")
        j["seller_hist_n_delivered"] = j.seller_hist_n_delivered.fillna(0)
        j["seller_hist_n_placed"] = j.seller_hist_n_placed.fillna(0)
        j["seller_hist_late_rate"] = j.seller_hist_late_rate.fillna(meta["prior_late_rate"])  # new seller -> prior
        out.loc[idx, cols] = j[cols].values
        metas.append({**meta, "rows": len(idx)})
    return pd.concat([f, out.astype(float)], axis=1), metas


def month_start(p: pd.Series) -> pd.Series:
    return p.dt.to_period("M").dt.to_timestamp()


def check_whitelist(X: pd.DataFrame) -> None:
    bad = (set(X.columns) - set(FEATURES)) | (set(X.columns) & FORBIDDEN)
    if bad:
        raise LeakageError(f"columns outside the whitelist: {sorted(bad)}")
