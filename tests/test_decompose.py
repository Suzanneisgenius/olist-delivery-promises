"""Centred state decomposition: identity, sign conventions, entry/exit, UNKNOWN, zero eligible."""
import pandas as pd
import pytest

from olist_analytics.decompose import NotComparable, decompose

W0, W1 = pd.Timestamp("2018-01-01"), pd.Timestamp("2018-01-08")


def sw(rows):
    return pd.DataFrame(rows, columns=["estimated_week", "customer_state_reported", "A", "L"])


def total(df, w):
    d = df[df.estimated_week == w]
    return d.A.sum() / (d.A + d.L).sum()


def test_same_states_identity_and_centring_keeps_mix_total():
    df = sw([(W0, "SP", 90, 10), (W0, "RJ", 40, 10), (W1, "SP", 60, 20), (W1, "RJ", 70, 10)])
    d, s = decompose(df, W0, W1, min_n_rank=0)
    assert d.total.sum() == pytest.approx(total(df, W1) - total(df, W0))
    # same state set: shares change by zero in total, so centring moves mix between states but not its sum
    uncentred = ((d.otd_prior + d.otd_current) / 2 * (d.share_current - d.share_prior)).sum()
    assert s["sum_mix"] == pytest.approx(uncentred)


def test_shift_toward_low_otd_state_has_negative_mix():
    df = sw([(W0, "HI", 98, 2), (W0, "LO", 80, 20), (W1, "HI", 49, 1), (W1, "LO", 120, 30)])
    d, _ = decompose(df, W0, W1, min_n_rank=0)
    d = d.set_index("customer_state_reported")
    assert d.loc["LO", "mix"] < 0 and d.loc["HI", "mix"] < 0     # both moves lower overall OTD
    assert d.performance.abs().max() == pytest.approx(0)


def test_entry_and_exit_are_centred_and_reconcile():
    df = sw([(W0, "SP", 90, 10), (W0, "AC", 5, 5), (W1, "SP", 85, 15), (W1, "RR", 9, 1)])
    d, s = decompose(df, W0, W1, min_n_rank=0)
    d = d.set_index("customer_state_reported")
    c = s["c"]
    assert d.loc["RR", "status"] == "entry" and d.loc["RR", "entry"] == pytest.approx((10 / 110) * (0.9 - c))
    assert d.loc["AC", "status"] == "exit" and d.loc["AC", "exit"] == pytest.approx(-(10 / 110) * (0.5 - c))
    assert d.total.sum() == pytest.approx(total(df, W1) - total(df, W0))


def test_uncentred_entry_exit_would_break_the_identity():
    df = sw([(W0, "SP", 90, 10), (W0, "AC", 5, 5), (W1, "SP", 85, 15), (W1, "RR", 18, 2)])
    d, s = decompose(df, W0, W1, min_n_rank=0)
    d = d.set_index("customer_state_reported")
    assert d.total.sum() == pytest.approx(s["change"])
    wrong = d.performance.sum() + d.mix.sum() + (20 / 120) * 0.9 - (10 / 110) * 0.5
    assert abs(wrong - s["change"]) > 0.01


def test_unknown_state_is_a_normal_group():
    df = sw([(W0, "SP", 90, 10), (W0, "UNKNOWN", 3, 0), (W1, "SP", 80, 20), (W1, "UNKNOWN", 2, 1)])
    d, _ = decompose(df, W0, W1, min_n_rank=0)
    assert "UNKNOWN" in set(d.customer_state_reported)


def test_zero_eligible_week_is_not_comparable():
    df = sw([(W0, "SP", 0, 0), (W1, "SP", 5, 5)])
    with pytest.raises(NotComparable):
        decompose(df, W0, W1)


def test_small_states_are_flagged_not_dropped():
    df = sw([(W0, "SP", 90, 10), (W0, "RR", 2, 0), (W1, "SP", 85, 15), (W1, "RR", 1, 1)])
    d, s = decompose(df, W0, W1, min_n_rank=30)
    assert bool(d.set_index("customer_state_reported").loc["RR", "small_sample"])
    assert d.total.sum() == pytest.approx(s["change"])
