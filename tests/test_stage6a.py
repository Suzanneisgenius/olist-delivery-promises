"""Stage 6a: missing delivery times are not all censoring; as-of states use only records before the cut."""
import pandas as pd
import pytest

from olist_analytics.survival_audit import (as_of, as_of_violations, deadline_days, final_category,
                                            observation_end, unresolved_table)

END = observation_end("2018-09-03")              # exclusive: 2018-09-04 00:00


def orders(rows):
    df = pd.DataFrame(rows, columns=["order_id", "order_status", "outcome_bucket", "order_purchase_timestamp",
                                     "order_delivered_customer_date", "order_estimated_delivery_date"])
    for c in df.columns[3:]:
        df[c] = pd.to_datetime(df[c], format="mixed")
    return df.set_index("order_id", drop=False)


def test_observation_end_conventions_are_explicit():
    assert observation_end("2018-09-03") == pd.Timestamp("2018-09-04")
    assert observation_end("2018-09-03", "midnight") == pd.Timestamp("2018-09-03")


def test_late_iff_delivery_time_reaches_deadline_so_p_late_is_survival_at_deadline():
    m = orders([("on_time_last_minute", "delivered", "A", "2018-03-01 10:00", "2018-03-08 23:59", "2018-03-08"),
                ("late_just_after_midnight", "delivered", "L", "2018-03-01 10:00", "2018-03-09 00:01", "2018-03-08")])
    dur = (m.order_delivered_customer_date - m.order_purchase_timestamp).dt.total_seconds() / 86400
    assert (dur >= deadline_days(m)).tolist() == [False, True] == (m.outcome_bucket == "L").tolist()


@pytest.fixture
def mixed():
    return orders([
        ("ev", "delivered", "A", "2018-08-01", "2018-08-10", "2018-08-20"),
        ("canceled_with_date", "canceled", "X", "2018-08-01", "2018-08-05", "2018-08-20"),
        ("unavailable", "unavailable", "X", "2018-08-01", None, "2018-08-20"),
        ("delivered_no_date", "delivered", "U", "2018-07-01", None, "2018-07-20"),
        ("u_recent", "shipped", "U", "2018-08-10", None, "2018-08-25"),
        ("u_stale", "shipped", "U", "2017-12-01", None, "2017-12-20"),
        ("u_bought_on_boundary_day", "shipped", "U", "2018-09-03 09:06:57", None, "2018-09-20"),
        ("no_estimate", "delivered", "NO_VALID_ESTIMATE", "2018-08-01", "2018-08-10", None),
    ])


def test_final_file_categories(mixed):
    c = final_category(mixed, END, stale_days=31)
    assert c.to_dict() == {"ev": "EVENT", "canceled_with_date": "CANCELED_OR_UNAVAILABLE",
                           "unavailable": "CANCELED_OR_UNAVAILABLE", "delivered_no_date": "DELIVERED_TIME_MISSING",
                           "u_recent": "RECENT_U_CANDIDATE", "u_stale": "U_STALE_MISSING_OUTCOME",
                           "u_bought_on_boundary_day": "RECENT_U_CANDIDATE", "no_estimate": "NO_VALID_ESTIMATE"}


def test_order_bought_after_a_midnight_cut_never_enters_the_risk_set(mixed):
    mid = observation_end("2018-09-03", "midnight")
    assert final_category(mixed, mid, 31)["u_bought_on_boundary_day"] == "PURCHASED_AT_OR_AFTER_OBSERVATION_END"
    a = as_of(mixed, mid)
    assert a.loc["u_bought_on_boundary_day", "as_of_state"] == "NOT_IN_RISK_SET"
    assert as_of_violations(mixed, a, mid) == []                          # no negative follow-up anywhere
    assert as_of(mixed, END).loc["u_bought_on_boundary_day", "follow_up_days"] > 0


def test_stale_u_is_never_a_censoring_candidate(mixed):
    for th in (31, 60, 72):
        assert final_category(mixed, END, th)["u_stale"] == "U_STALE_MISSING_OUTCOME"


def test_delivery_after_the_cut_is_unresolved_at_the_cut_not_an_event():
    m = orders([("late_record", "delivered", "A", "2018-08-20", "2018-09-05 10:00", "2018-09-10")])
    assert final_category(m, END, 31)["late_record"] == "EVENT"                 # final file
    a = as_of(m, END)
    assert a.loc["late_record", "as_of_state"] == "UNRESOLVED_AT_CUT"            # as of the cut: censored
    assert a.loc["late_record", "follow_up_days"] == pytest.approx(15.0)


def test_canceled_order_with_a_record_before_the_cut_is_a_conflict_not_open_and_not_an_event(mixed):
    a = as_of(mixed, "2018-08-15")
    assert a.loc["canceled_with_date", "as_of_state"] == "RECORD_STATUS_CONFLICT"
    assert a.loc["ev", "as_of_state"] == "EVENT_RECORDED"
    assert a.loc["unavailable", "as_of_state"] == "UNRESOLVED_AT_CUT"


def test_guards_catch_entry_after_cut_and_non_positive_times(mixed):
    cut = pd.Timestamp("2018-08-15")
    a = as_of(mixed, cut)
    tampered = a.copy()
    tampered.loc["u_bought_on_boundary_day", "as_of_state"] = "UNRESOLVED_AT_CUT"
    assert "order in risk set purchased at/after the cut" in as_of_violations(mixed, tampered, cut)
    tampered = a.copy()
    tampered.loc["ev", "duration_days"] = 0.0
    assert "non-positive event duration" in as_of_violations(mixed, tampered, cut)


def test_unresolved_table_keeps_conflicts_out_of_unresolved():
    m = orders([("done", "delivered", "A", "2018-03-01", "2018-03-10", "2018-03-20"),
                ("late_open", "delivered", "L", "2018-03-01", "2018-04-15", "2018-03-20"),
                ("cancel_open", "canceled", "X", "2018-03-15", None, "2018-04-10"),
                ("cancel_with_record", "canceled", "X", "2018-03-02", "2018-03-12", "2018-03-25"),
                ("after", "delivered", "A", "2018-04-02", "2018-04-10", "2018-04-20")])
    t = unresolved_table(m, ["2018-04-01"]).iloc[0]
    assert (t.in_risk_set, t.event_recorded_before_T, t.record_status_conflict, t.unresolved_at_T) == (4, 1, 1, 2)
    assert (t.later_final_L, t.later_final_X, t.deadline_passed_at_T) == (1, 1, 1)
