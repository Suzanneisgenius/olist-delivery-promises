"""Leakage and protocol tests for stage 3 (hand-built, no real data)."""
import numpy as np
import pandas as pd
import pytest

from olist_analytics.features import (FEATURES, LeakageError, assign_split, attach_seller, check_whitelist,
                                      seller_snapshot)
from olist_analytics.modeling import logistic, top_share_by_week

T = pd.Timestamp


def hist(rows):
    """rows: (order_id, seller, purchased, delivered, bucket)"""
    d = pd.DataFrame(rows, columns=["order_id", "single_seller_id", "order_purchase_timestamp",
                                    "order_delivered_customer_date", "outcome_bucket"])
    for c in ["order_purchase_timestamp", "order_delivered_customer_date"]:
        d[c] = pd.to_datetime(d[c])
    d["is_late"] = (d.outcome_bucket == "L").astype(float)
    d["handling_hours"] = 24.0
    d["is_stage_eligible"] = True
    return d


H = hist([
    ("a", "s1", "2018-01-02", "2018-01-10", "L"),    # known before Feb 1
    ("b", "s1", "2018-01-20", "2018-02-05", "L"),    # bought before Feb 1 but delivered after -> unknown at Feb 1
    ("c", "s1", "2018-01-05", "2018-01-12", "A"),
    ("d", "s2", "2018-01-03", "2018-01-09", "A"),
])


def test_snapshot_uses_delivery_time_not_purchase_time():
    snap, meta = seller_snapshot(H, T("2018-02-01"), k=0)
    s1 = snap.loc["s1"]
    assert s1.seller_hist_n_delivered == 2 and s1.seller_hist_late_rate == pytest.approx(0.5)  # a + c, not b
    assert s1.seller_hist_n_placed == 3                                                     # volume placed is known
    assert pd.Timestamp(meta["max_label_delivery"]) < T("2018-02-01")


def test_changing_a_future_label_does_not_change_past_features():
    snap1, _ = seller_snapshot(H, T("2018-02-01"), k=20)
    H2 = H.copy()
    H2.loc[H2.order_id == "b", ["outcome_bucket", "is_late"]] = ["A", 0.0]
    snap2, _ = seller_snapshot(H2, T("2018-02-01"), k=20)
    pd.testing.assert_frame_equal(snap1, snap2)


def test_new_seller_gets_prior_and_smoothing_shrinks():
    rows = pd.DataFrame({"order_purchase_timestamp": pd.to_datetime(["2018-02-03", "2018-02-04"]),
                         "single_seller_id": ["s1", "s9"]}, index=[10, 11])
    f = pd.DataFrame(index=rows.index)
    X, metas = attach_seller(rows, f, H, pd.Series(T("2018-02-01"), index=rows.index), k=20)
    prior = metas[0]["prior_late_rate"]                     # 1 late of 3 known
    assert prior == pytest.approx(1 / 3)
    assert X.loc[11, "seller_hist_late_rate"] == pytest.approx(prior) and X.loc[11, "seller_hist_n_delivered"] == 0
    assert X.loc[10, "seller_hist_late_rate"] == pytest.approx((1 + 20 * prior) / (2 + 20))


def test_row_scored_before_its_snapshot_is_rejected():
    rows = pd.DataFrame({"order_purchase_timestamp": [T("2018-01-15")], "single_seller_id": ["s1"]}, index=[0])
    with pytest.raises(LeakageError):
        attach_seller(rows, pd.DataFrame(index=rows.index), H, pd.Series(T("2018-02-01"), index=rows.index), k=20)


def test_target_order_never_feeds_its_own_feature():
    # snapshot at month start <= purchase < delivery, so the row's own label cannot be known
    snap, _ = seller_snapshot(H, T("2018-01-01"), k=0)
    assert "s1" not in snap.index or snap.loc["s1"].seller_hist_n_delivered == 0


def test_whitelist_rejects_forbidden_columns():
    X = pd.DataFrame({c: [0] for c in FEATURES}).assign(order_delivered_carrier_date=0)
    with pytest.raises(LeakageError):
        check_whitelist(X)


def test_split_boundaries():
    p = pd.to_datetime(pd.Series(["2017-12-31 23:59", "2018-01-01 00:00", "2018-03-31 23:59", "2018-04-01 00:00"]))
    assert assign_split(p).tolist() == ["train", "dev", "dev", "test"]


def test_top_share_uses_floor_per_week_and_counts_hits():
    y = [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]   # week A has 10 rows, week B 9 rows
    s = [.9] + [.1] * 9 + [.8] + [.1] * 8
    w = ["A"] * 10 + ["B"] * 9
    r = top_share_by_week(y, s, w, 0.10)
    assert r["selected"] == 1 and r["true_late_in_selected"] == 1   # floor(1.0)=1 in A, floor(0.9)=0 in B
    assert r["recall_at_top"] == pytest.approx(0.5)


def test_preprocessing_is_fit_on_training_rows_only():
    rng = np.random.default_rng(0)
    Xtr = pd.DataFrame({c: rng.normal(size=200) for c in FEATURES[:-3]})
    for c in FEATURES[-3:]:
        Xtr[c] = "SP"
    Xtr.loc[:9, "distance_km"] = np.nan
    ytr = (rng.random(200) < 0.2).astype(int)
    pipe = logistic(1.0).fit(Xtr, ytr)
    imp = pipe.named_steps["pre"].named_transformers_["skew"].named_steps["imp"]
    col = list(pipe.named_steps["pre"].transformers_[0][2]).index("distance_km")
    assert imp.statistics_[col] == pytest.approx(Xtr.distance_km.median())


def test_future_development_labels_cannot_select_parameters():
    from olist_analytics.features import selection_labels_known_before
    dev = hist([("known", "s1", "2018-03-01", "2018-03-20", "A"),
                ("pending", "s1", "2018-03-15", "2018-04-02", "L"),
                ("boundary", "s2", "2018-03-10", "2018-04-01", "L")])
    selected = selection_labels_known_before(dev, T("2018-04-01"))
    assert selected.order_id.tolist() == ["known"]
    dev.loc[dev.order_id != "known", ["outcome_bucket", "is_late"]] = ["A", 0.]
    pd.testing.assert_frame_equal(selected, selection_labels_known_before(dev, T("2018-04-01")))


def test_invalid_stage_history_does_not_contaminate_handling_feature():
    h = H.copy()
    h.loc[h.order_id == "a", ["handling_hours", "is_stage_eligible"]] = [-999., False]
    snap, meta = seller_snapshot(h, T("2018-02-01"), k=0)
    assert snap.loc["s1", "seller_hist_late_rate"] == .5
    assert snap.loc["s1", "seller_hist_handling_median_h"] == 24.
    assert meta["handling_history_excluded_invalid_stage"] == 1
