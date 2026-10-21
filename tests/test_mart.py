"""orders_mart rules, checked against hand-computed values."""
import pandas as pd
import pytest

from olist_analytics.mart import JoinFanOut, build_orders_mart, geo_lookup, join_checked


@pytest.fixture
def built(tables):
    mart, codes, extra = build_orders_mart(tables)
    return mart.set_index("order_id"), codes, extra


def has(codes, oid, code):
    return ((codes.order_id == oid) & (codes.reason_code == code)).any()


def test_one_row_per_order_and_no_amount_doubling(built):
    m, _, _ = built
    assert m.index.is_unique and len(m) == 7
    o1 = m.loc["o1"]
    assert o1.items_price_sum == 20.0 and o1.items_freight_sum == 4.0     # 2 lines, not 2 x 2
    assert o1.payment_value_sum == 24.0 and o1.n_payments == 2


def test_order_item_id_keeps_repeated_product_lines(built):
    o1 = built[0].loc["o1"]
    assert o1.n_item_lines == 2 and o1.n_distinct_products == 1


def test_on_time_is_compared_by_calendar_day(built):
    m = built[0]
    assert m.loc["o1", "outcome_bucket"] == "A" and m.loc["o1", "days_late"] == 0   # 18:00 on the estimated day
    assert m.loc["o2", "outcome_bucket"] == "L" and m.loc["o2", "days_late"] == 1


def test_stage_anomaly_keeps_order_in_otd(built):
    m, codes, _ = built
    assert has(codes, "o3", "carrier_before_approved")
    assert m.loc["o3", "is_otd_eligible"] and not m.loc["o3", "is_stage_eligible"]


def test_delivered_without_date_is_unconfirmed_not_labelled(built):
    m, codes, _ = built
    assert m.loc["o4", "outcome_bucket"] == "U" and pd.isna(m.loc["o4", "is_late"])
    assert has(codes, "o4", "delivered_missing_date")


def test_canceled_and_in_progress_buckets(built):
    m, codes, _ = built
    assert m.loc["o5", "outcome_bucket"] == "X" and has(codes, "o5", "canceled_with_delivery_date")
    assert m.loc["o6", "outcome_bucket"] == "U"


def test_buckets_are_exclusive_and_reasons_may_overlap(built):
    m, codes, _ = built
    assert m.outcome_bucket.value_counts().sum() == len(m)
    assert codes.groupby("order_id").size().max() >= 1


def test_multi_seller_has_no_single_seller_or_distance(built):
    m, codes, _ = built
    assert m.loc["o7", "n_sellers"] == 2 and pd.isna(m.loc["o7", "single_seller_id"])
    assert pd.isna(m.loc["o7", "distance_km"]) and not m.loc["o7", "is_model_eligible_prelim"]


def test_stage_identity_holds(built):
    m = built[0]
    s = m[m.is_stage_eligible]
    gap = (s.total_hours - s.approval_hours - s.handling_hours - s.transit_hours).abs().max()
    assert gap == pytest.approx(0)


def test_review_primary_is_first_answered_after_delivery(built):
    m = built[0]
    assert m.loc["o2", "review_id_primary"] == "r2" and m.loc["o2", "review_score_primary"] == 1
    assert m.loc["o2", "review_score_latest"] == 2 and m.loc["o2", "n_reviews"] == 3
    assert not m.loc["o4", "is_review_eligible"]


def test_geo_excludes_out_of_brazil_points_and_keeps_leading_zeros(tables):
    look, stats = geo_lookup(tables["geolocation"])
    row = look.set_index("zip_prefix").loc["01001"]
    assert stats["out_of_bbox_rows"] == 1 and row.n_points == 2
    assert row.lat == pytest.approx(-23.555)


def test_join_checked_refuses_fan_out():
    left = pd.DataFrame({"k": [1, 2]})
    with pytest.raises(JoinFanOut):
        join_checked(left, pd.DataFrame({"k": [1, 1], "v": [0, 1]}), "k")


def test_estimate_before_purchase_is_not_labelled(tables):
    tables["orders"].loc[tables["orders"].order_id == "o2", "order_estimated_delivery_date"] = pd.Timestamp("2018-02-27")
    m, codes, _ = build_orders_mart(tables)
    m = m.set_index("order_id")
    assert m.loc["o2", "outcome_bucket"] == "NO_VALID_ESTIMATE" and pd.isna(m.loc["o2", "estimated_week"])
    assert not m.loc["o2", "is_otd_eligible"] and has(codes, "o2", "estimated_before_purchase")
    assert pd.isna(m.loc["o2", "days_late"])                     # no diagnostic value on an invalid estimate


def test_missing_customer_kept_as_unknown_state(tables):
    tables["customers"] = tables["customers"][tables["customers"].customer_id != "c1"]
    m, codes, _ = build_orders_mart(tables)
    m = m.set_index("order_id")
    assert m.loc["o1", "customer_state_reported"] == "UNKNOWN" and m.loc["o1", "is_otd_eligible"]
    assert has(codes, "o1", "missing_customer_record")


def test_weekly_totals_plus_unassigned_equal_mart(tables):
    from olist_analytics.cohort import weekly_buckets
    tables["orders"].loc[tables["orders"].order_id == "o2", "order_estimated_delivery_date"] = pd.Timestamp("2018-02-27")
    m, _, _ = build_orders_mart(tables)
    w, unassigned = weekly_buckets(m)
    assert w.orders.sum() + unassigned == len(m) and unassigned == 1
