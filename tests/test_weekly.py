import pandas as pd
import pytest

from olist_analytics.weekly import seller_summary, stage_diagnosis


def test_single_seller_queue_denominators_and_sample_flag(tables):
    from olist_analytics.mart import build_orders_mart
    m, _, _ = build_orders_mart(tables)
    weeks = m.estimated_week.dropna().unique()
    q = seller_summary(m, weeks, min_n=30)
    expected = m[m.estimated_week.isin(weeks) & m.single_seller_id.notna() & m.is_otd_eligible]
    assert q.eligible_orders.sum() == len(expected)
    assert (q.A+q.L).equals(q.eligible_orders)
    assert not q.meets_min_n.any()
    assert q.otd_wilson_low.between(0,1).all() and q.otd_wilson_high.between(0,1).all()
    assert (q.otd_wilson_low <= q.otd_rate).all() and (q.otd_wilson_high >= q.otd_rate).all()
    assert m.loc[m.n_sellers > 1, 'single_seller_id'].isna().all()


def test_stage_diagnosis_excludes_invalid_and_unconfirmed_orders(tables):
    from olist_analytics.mart import build_orders_mart
    m, _, _ = build_orders_mart(tables)
    weeks = m.estimated_week.dropna().unique()
    dist, lim = stage_diagnosis(m, weeks)
    base = m[m.estimated_week.isin(weeks) & m.is_stage_eligible & m.is_otd_eligible]
    assert dist.loc[dist.stage == 'total', 'n'].sum() == len(base)
    assert lim.orders.sum() <= len(base)


def test_wilson_interval_for_one_observed_success():
    m = pd.DataFrame({'estimated_week':[pd.Timestamp('2018-01-01')], 'single_seller_id':['s'],
                      'seller_state':['SP'], 'outcome_bucket':['A'], 'is_otd_eligible':[True],
                      'is_stage_eligible':[True], 'handling_hours':[10.], 'transit_hours':[20.]})
    q = seller_summary(m, list(m.estimated_week), min_n=1).iloc[0]
    assert q.otd_rate == 1
    assert q.otd_wilson_low == pytest.approx(0.2065493144)
    assert q.otd_wilson_high == pytest.approx(1)
