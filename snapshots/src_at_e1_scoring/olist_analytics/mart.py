"""Build orders_mart: exactly one row per order_id.

Rules
  * Every input is aggregated to its declared grain BEFORE it is joined, and every
    join goes through join_checked(), which fails on fan-out.
  * Quality problems do not delete orders. They add reason codes, and each use
    (OTD, stage timing, model, review) has its own eligibility flag.
  * outcome_bucket is mutually exclusive: A on time | L late | U outcome unconfirmed |
    X canceled/unavailable | NO_VALID_ESTIMATE (missing, or earlier than purchase).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .io import ASSUMPTIONS

REASON_AFFECTS = {
    "no_items": "model",
    "multi_seller": "model",
    "missing_approved_at": "stage",
    "approved_before_purchase": "stage",
    "missing_carrier_date": "stage",
    "carrier_before_approved": "stage",
    "carrier_before_purchase": "stage",
    "delivered_before_carrier": "stage",
    "delivered_missing_date": "otd,stage",
    "delivered_before_purchase": "otd,stage",
    "canceled_with_delivery_date": "otd",
    "estimated_before_purchase": "otd",
    "missing_customer_record": "state (reported as UNKNOWN)",
    "missing_customer_geo": "distance",
    "missing_seller_geo": "distance",
    "dispersed_geo_prefix": "distance (flag only)",
    "missing_product_weight": "weight (flag only)",
    "payment_mismatch": "info",
    "no_payment": "info",
    "no_review_after_delivery": "review",
}
IN_PROGRESS = {"shipped", "invoiced", "processing", "created", "approved"}


class JoinFanOut(AssertionError):
    pass


def join_checked(left: pd.DataFrame, right: pd.DataFrame, on, how="left", name="") -> pd.DataFrame:
    """Many-to-one join that refuses to change the left row count."""
    keys = [on] if isinstance(on, str) else list(on)
    if right.duplicated(keys).any():
        raise JoinFanOut(f"{name}: right side has duplicate keys {keys}")
    out = left.merge(right, on=keys, how=how, validate="many_to_one")
    if len(out) != len(left):
        raise JoinFanOut(f"{name}: row count changed {len(left)} -> {len(out)}")
    return out


def week_start(s: pd.Series) -> pd.Series:
    d = s.dt.normalize()
    return d - pd.to_timedelta(d.dt.weekday, unit="D")


def haversine_km(lat1, lng1, lat2, lng2):
    lat1, lng1, lat2, lng2 = map(np.radians, (lat1, lng1, lat2, lng2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lng2 - lng1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


# ------------------------------------------------------------------ per-grain inputs
def item_features(items: pd.DataFrame, products: pd.DataFrame) -> pd.DataFrame:
    """order_items (order_id + order_item_id) -> one row per order_id."""
    p = products[["product_id", "product_category_name", "product_weight_g"]]
    it = join_checked(items, p, "product_id", name="items->products")
    it["weight_missing"] = it.product_weight_g.isna()
    g = it.groupby("order_id")
    out = pd.DataFrame({
        "n_item_lines": g.size(),
        "n_distinct_products": g.product_id.nunique(),
        "n_sellers": g.seller_id.nunique(),
        "n_categories": g.product_category_name.nunique(),
        "items_price_sum": g.price.sum(),
        "items_freight_sum": g.freight_value.sum(),
        "weight_g_sum": g.product_weight_g.sum(min_count=1),
        "weight_missing_lines": g.weight_missing.sum(),
        "shipping_limit_min": g.shipping_limit_date.min(),
        "single_seller_id": g.seller_id.agg(lambda s: s.iloc[0] if s.nunique() == 1 else None),
    })
    top = it.sort_values(["order_id", "price", "order_item_id"], ascending=[True, False, True]) \
            .drop_duplicates("order_id").set_index("order_id").product_category_name
    out["top_price_category"] = top
    return out.reset_index()


def payment_features(pay: pd.DataFrame) -> pd.DataFrame:
    g = pay.groupby("order_id")
    return pd.DataFrame({"n_payments": g.size(), "payment_value_sum": g.payment_value.sum()}).reset_index()


def geo_lookup(geo: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """zip prefix -> median point of in-Brazil points, with a dispersion flag."""
    b = ASSUMPTIONS["geo"]["brazil_bbox"]
    inside = (geo.geolocation_lat.between(b["lat_min"], b["lat_max"])
              & geo.geolocation_lng.between(b["lng_min"], b["lng_max"]))
    g = geo[inside]
    med = g.groupby("geolocation_zip_code_prefix")[["geolocation_lat", "geolocation_lng"]].median()
    med.columns = ["lat", "lng"]
    j = g.join(med, on="geolocation_zip_code_prefix")
    j["d"] = haversine_km(j.geolocation_lat, j.geolocation_lng, j.lat, j.lng)
    disp = j.groupby("geolocation_zip_code_prefix").agg(n_points=("d", "size"), median_dev_km=("d", "median"),
                                                       p95_dev_km=("d", lambda x: x.quantile(0.95)))
    look = med.join(disp).reset_index().rename(columns={"geolocation_zip_code_prefix": "zip_prefix"})
    look["dispersed"] = look.p95_dev_km > ASSUMPTIONS["geo"]["dispersion_flag_km"]
    stats = {"rows": len(geo), "out_of_bbox_rows": int((~inside).sum()), "prefixes": len(look),
             "dispersed_prefixes": int(look.dispersed.sum())}
    return look, stats


def select_reviews(reviews: pd.DataFrame, delivered_at: pd.Series) -> pd.DataFrame:
    """Primary: first review ANSWERED on/after delivery. Sensitivity: latest answered review."""
    r = reviews.join(delivered_at.rename("delivered_at"), on="order_id")
    r = r.sort_values(["order_id", "review_answer_timestamp", "review_id"])
    after = r[r.delivered_at.notna() & (r.review_answer_timestamp >= r.delivered_at)]
    first = after.drop_duplicates("order_id", keep="first").set_index("order_id")
    latest = r.drop_duplicates("order_id", keep="last").set_index("order_id")
    n = r.groupby("order_id").size()
    out = pd.DataFrame({"n_reviews": n})
    out["review_id_primary"] = first.review_id
    out["review_score_primary"] = first.review_score
    out["review_answer_ts_primary"] = first.review_answer_timestamp
    out["review_score_latest"] = latest.review_score
    return out.reset_index()


# ------------------------------------------------------------------ order mart
def build_orders_mart(t: dict[str, pd.DataFrame]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    o = t["orders"].drop(columns="source_record_no").copy()
    n0 = len(o)
    cust = t["customers"][["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_state"]]
    o = join_checked(o, cust, "customer_id", name="orders->customers")
    o = join_checked(o, item_features(t["order_items"], t["products"]), "order_id", name="orders->item_features")
    o = join_checked(o, payment_features(t["order_payments"]), "order_id", name="orders->payments")
    sell = t["sellers"][["seller_id", "seller_zip_code_prefix", "seller_state"]].rename(columns={"seller_id": "single_seller_id"})
    o = join_checked(o, sell, "single_seller_id", name="orders->sellers")

    look, geo_stats = geo_lookup(t["geolocation"])
    gl = look[["zip_prefix", "lat", "lng", "dispersed"]]
    o = join_checked(o, gl.rename(columns={"zip_prefix": "customer_zip_code_prefix", "lat": "cust_lat",
                                           "lng": "cust_lng", "dispersed": "cust_geo_dispersed"}),
                     "customer_zip_code_prefix", name="orders->customer_geo")
    o = join_checked(o, gl.rename(columns={"zip_prefix": "seller_zip_code_prefix", "lat": "seller_lat",
                                           "lng": "seller_lng", "dispersed": "seller_geo_dispersed"}),
                     "seller_zip_code_prefix", name="orders->seller_geo")
    o["distance_km"] = haversine_km(o.cust_lat, o.cust_lng, o.seller_lat, o.seller_lng)

    # --- timestamps and outcome
    P, A_, C, D, E = (o.order_purchase_timestamp, o.order_approved_at, o.order_delivered_carrier_date,
                      o.order_delivered_customer_date, o.order_estimated_delivery_date)
    status = o.order_status
    delivered = status.eq("delivered")
    valid_delivery = delivered & D.notna() & (D >= P)
    bad_estimate = E.isna() | (E.dt.normalize() < P.dt.normalize())
    o["estimated_week"] = week_start(E).where(~bad_estimate)
    o["customer_state_reported"] = o.customer_state.fillna("UNKNOWN")   # keeps orders in state totals
    o["days_late"] = (D.dt.normalize() - E.dt.normalize()).dt.days.where(valid_delivery & ~bad_estimate)
    bucket = np.select(
        [bad_estimate, status.isin(["canceled", "unavailable"]), valid_delivery & (D.dt.normalize() <= E),
         valid_delivery],
        ["NO_VALID_ESTIMATE", "X", "A", "L"], default="U")
    o["outcome_bucket"] = bucket
    o["is_late"] = pd.Series(np.where(bucket == "L", 1.0, np.where(bucket == "A", 0.0, np.nan)), index=o.index)

    hrs = lambda a, b: (b - a).dt.total_seconds() / 3600
    o["approval_hours"] = hrs(P, A_)
    o["handling_hours"] = hrs(A_, C)            # payment approved -> handed to carrier
    o["transit_hours"] = hrs(C, D)              # handed to carrier -> delivered
    o["total_hours"] = hrs(P, D)

    # --- reason codes (may overlap)
    rc = {
        "no_items": o.n_item_lines.isna(),
        "multi_seller": o.n_sellers.fillna(0) > 1,
        "missing_approved_at": delivered & A_.isna(),
        "approved_before_purchase": A_.notna() & (A_ < P),
        "missing_carrier_date": delivered & C.isna(),
        "carrier_before_approved": C.notna() & A_.notna() & (C < A_),
        "carrier_before_purchase": C.notna() & (C < P),
        "delivered_before_carrier": D.notna() & C.notna() & (D < C),
        "delivered_missing_date": delivered & D.isna(),
        "delivered_before_purchase": D.notna() & (D < P),
        "canceled_with_delivery_date": status.eq("canceled") & D.notna(),
        "estimated_before_purchase": E.notna() & (E.dt.normalize() < P.dt.normalize()),
        "missing_customer_record": o.customer_unique_id.isna(),
        "missing_customer_geo": o.cust_lat.isna(),
        "missing_seller_geo": o.single_seller_id.notna() & o.seller_lat.isna(),
        "dispersed_geo_prefix": o.cust_geo_dispersed.eq(True) | o.seller_geo_dispersed.eq(True),
        "missing_product_weight": o.weight_missing_lines.fillna(0) > 0,
        "payment_mismatch": o.payment_value_sum.notna() & o.items_price_sum.notna() & (
            (o.payment_value_sum - o.items_price_sum - o.items_freight_sum).abs() > ASSUMPTIONS["quality"]["payment_mismatch_tolerance_brl"]),
        "no_payment": o.payment_value_sum.isna(),
    }

    # --- reviews (needs valid delivery time)
    rv = select_reviews(t["order_reviews"], o.set_index("order_id").order_delivered_customer_date.where(
        valid_delivery.values))
    o = join_checked(o, rv, "order_id", name="orders->review_selection")
    o["n_reviews"] = o.n_reviews.fillna(0).astype(int)
    rc["no_review_after_delivery"] = valid_delivery & o.review_id_primary.isna()

    codes = pd.DataFrame(rc)
    o["reason_codes"] = codes.apply(lambda r: ";".join(codes.columns[r.values]), axis=1)

    stage_bad = codes[["missing_approved_at", "approved_before_purchase", "missing_carrier_date",
                       "carrier_before_approved", "carrier_before_purchase", "delivered_before_carrier",
                       "delivered_missing_date", "delivered_before_purchase"]].any(axis=1)
    o["is_otd_eligible"] = o.outcome_bucket.isin(["A", "L"])
    o["is_stage_eligible"] = valid_delivery & A_.notna() & C.notna() & ~stage_bad
    o["is_model_eligible_prelim"] = o.is_otd_eligible & o.n_sellers.eq(1)
    o["is_review_eligible"] = o.review_id_primary.notna()

    assert len(o) == n0 and o.order_id.is_unique, "orders_mart must have one row per order"
    long = codes.assign(order_id=o.order_id).melt("order_id", var_name="reason_code", value_name="hit")
    long = long[long.hit].drop(columns="hit")
    long["affects"] = long.reason_code.map(REASON_AFFECTS)
    return o, long.reset_index(drop=True), {"geo": geo_stats, "geo_lookup": look}
