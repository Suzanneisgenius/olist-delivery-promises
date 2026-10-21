"""Tests for the post-hoc rounding rules (scripts/e1_rounding_rules.py). Synthetic data only."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import e1_rounding_rules as R  # noqa: E402

from olist_analytics import e1_models as M  # noqa: E402


def cover(y, d):
    return float(np.mean(np.asarray(y) <= d))


# --- the counterexample from the fourth review ------------------------------------------------------------------
@pytest.mark.parametrize("pred_value", [0.0, 0.5])          # integer and non-integer constant predictor
def test_constant_delivery_counterexample(pred_value):
    y = np.full(200, 10.0); p = np.full(200, pred_value)
    s = R.shift(y, p, 0.90)                                  # = 10 - pred_value, so U = 10 for every order
    assert cover(y, R.promise(p, s, "ceil")) == 1.0
    assert cover(y, R.promise(p, s, "floor")) == 1.0
    assert cover(y, R.promise(p, s, "minus_one")) == 0.0      # "subtract one day" covers nobody


def test_floor_and_minus_one_differ_only_on_whole_number_bounds():
    rng = np.random.default_rng(1)
    p = rng.uniform(0, 30, 5000); p[:50] = np.round(p[:50])  # 50 bounds land on whole numbers
    s = 3.0
    diff = R.promise(p, s, "floor") != R.promise(p, s, "minus_one")
    assert np.array_equal(diff, R.on_integer_boundary(p, s))
    assert diff.sum() == 50


@pytest.mark.parametrize("seed", range(20))
def test_floor_keeps_the_continuous_coverage_event_on_calibration(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(50, 3000))
    x = rng.uniform(0, 1, n)
    y = np.maximum(1, np.ceil(np.exp(2 + 0.5 * x + 0.4 * rng.standard_normal(n))))
    p = np.exp(2 + 0.5 * x) * rng.uniform(0.8, 1.2)          # continuous, deliberately mis-scaled
    for q in (0.8, 0.9, 0.95):
        s = R.shift(y, p, q)
        k = int(np.ceil((n + 1) * q))
        event = cover(y, p + s + R.TOL)                       # share with Y <= U
        assert cover(y, R.promise(p, s, "floor")) == event    # identical event (Y integer)
        assert event >= k / n - 1e-12                         # the rank argument on the calibration set
        assert cover(y, R.promise(p, s, "ceil")) >= event     # ceil only adds slack
        assert cover(y, R.promise(p, s, "minus_one")) < k / n # here every U > 1: loses the k-th order (its U = Y_(k))


def test_floor_never_longer_than_ceil_and_at_most_one_day_shorter():
    rng = np.random.default_rng(7)
    p = rng.uniform(-5, 40, 10000); s = 2.37
    c, f = R.promise(p, s, "ceil"), R.promise(p, s, "floor")
    assert np.all(f <= c) and np.all(c - f <= 1) and np.all(f >= 1)


def test_tolerance_keeps_bounds_that_should_be_whole_numbers():
    # 0.1 + 0.2 = 0.30000000000000004; scaled bounds that should be integers come out just above or below
    p = np.array([0.1 * 3, 2.9999999999999996, 7.000000000000001]); s = 0.0
    assert list(R.promise(p, s, "floor")) == [1, 3, 7]
    assert list(R.promise(p, s, "ceil")) == [1, 3, 7]


def test_shift_matches_registered_function():
    rng = np.random.default_rng(3)
    y = np.maximum(1, np.ceil(rng.gamma(3, 4, 17056))); p = rng.uniform(5, 20, 17056)
    assert R.shift(y, p, 0.90) == M.shift(y, p, 0.90)
    assert np.array_equal(R.promise(p, M.shift(y, p, 0.9), "ceil"), M.promise(p, M.shift(y, p, 0.9)))


@pytest.mark.parametrize("bad", [np.nan, np.inf])
def test_rules_refuse_bad_input(bad):
    y, p = np.arange(1.0, 101.0), np.full(100, 5.0)
    p[3] = bad
    with pytest.raises(ValueError):
        R.shift(y, p, 0.9)
    with pytest.raises(ValueError):
        R.promise(p, 1.0, "floor")
    with pytest.raises(ValueError):
        R.shift(y, np.full(99, 5.0), 0.9)
    with pytest.raises(ValueError):
        R.promise(np.full(3, 5.0), 1.0, "round")


# --- the one-day minimum (fifth review) --------------------------------------------------------------------------
def test_minimum_can_rescue_minus_one_at_one_day():
    # 100 orders of 1 day, prediction 0.5, q = 0.9: k = 91, s = 0.5, U = 1 for every order
    y, p = np.ones(100), np.full(100, 0.5)
    s = R.shift(y, p, 0.90)
    assert s == 0.5
    assert cover(y, R.promise(p, s, "minus_one")) == 1.0      # max(1, ceil(0)) = 1: NOT below k / n here
    assert cover(y, R.promise(p, s, "floor")) == 1.0


def test_minimum_enlarges_the_floor_event():
    # Y = 1 everywhere, predictions 0..99: the continuous bound covers 91%, the floor promise with the minimum 100%
    y, p = np.ones(100), np.arange(100.0)
    s = R.shift(y, p, 0.90)
    u_event = cover(y, p + s + R.TOL)
    assert abs(u_event - 0.91) < 1e-12
    assert cover(y, R.promise(p, s, "floor")) == 1.0          # >= the event of U, not equal to it
    assert cover(y, np.floor(p + s + R.TOL)) == u_event       # untruncated floor: exactly the event of U


@pytest.mark.parametrize("u, y, floor_d, minus_d", [(0.4, 1, 1, 1), (1.0, 1, 1, 1), (2.0, 2, 2, 1), (1.7, 1, 1, 1)])
def test_boundary_cells(u, y, floor_d, minus_d):
    p = np.array([u]); s = 0.0
    assert R.promise(p, s, "floor")[0] == floor_d
    assert R.promise(p, s, "minus_one")[0] == minus_d
    assert (y <= R.promise(p, s, "floor")[0]) >= (y <= u + R.TOL)  # the minimum only enlarges the event


# --- input guards (fifth review) ----------------------------------------------------------------------------------
@pytest.mark.parametrize("bad_shift", [np.nan, np.inf, -np.inf, np.array([1.0, 2.0]), "x"])
def test_promise_refuses_bad_shift(bad_shift):
    with pytest.raises((ValueError, TypeError)):
        R.promise(np.array([10.0]), bad_shift, "floor")
    with pytest.raises((ValueError, TypeError)):
        R.on_integer_boundary(np.array([10.0]), bad_shift)


@pytest.mark.parametrize("pred", [np.array([]), np.ones((2, 2)), np.array([1.0, np.nan])])
def test_promise_refuses_bad_pred_shape(pred):
    with pytest.raises(ValueError):
        R.promise(pred, 1.0, "floor")


def test_promise_refuses_overflowing_sum():
    with pytest.raises(ValueError):
        R.promise(np.array([1.7e308]), 1.7e308, "floor")


@pytest.mark.parametrize("y", [np.array([1.5, 2.0, 3.0]), np.array([0.0, 2.0, 3.0])])
def test_shift_refuses_non_integer_or_zero_labels(y):
    with pytest.raises(ValueError):
        R.shift(y, np.zeros(3), 0.5)
