"""POST-HOC (2026-10-21, fourth review). Three ways to turn a continuous calibrated upper bound into a whole-day promise.

Not part of the registered E1 code (src/ is sealed); used only by scripts/e1_posthoc_methods.py and its tests.

Setup. Calibration residuals R_i = Y_i - f(X_i), k = ceil((n + 1) q), shift s = R_(k), bound U(x) = f(x) + s.
Y is a whole number of days (contract: labels passed to `shift` must be whole numbers >= 1; checked there).

    ceil      (registered)   d = max(1, ceil(U))        Y <= U  implies  Y <= d       (may add up to 1 day of slack)
    floor     (post hoc)     d = max(1, floor(U))
    minus_one (reviewer)     d = max(1, ceil(U - 1))    equals floor(U) unless U is a whole number; then one day less

Untruncated, for whole-number Y:  Y <= U  if and only if  Y <= floor(U).  So floor(U) keeps exactly the coverage
event of the continuous bound. The one-day minimum max(1, .) can only ENLARGE that event (e.g. Y = 1 and U < 1:
not covered by U, covered by the promise of 1 day), so with the minimum the event is at least, not exactly, that of U.
minus_one is not coverage-preserving in general: without the minimum its event is Y < U, i.e. R_i < R_(k) on the
calibration set, fewer than k orders. With the minimum this can fail to bite: Y = 1, U = 1 gives max(1, 0) = 1,
which covers. So minus_one may, but need not, fall below k / n.

Floating point: U = f + s is rounded, so a bound that should equal a whole number m can come out as m - 1e-13.
All rules therefore compare against U +/- TOL with TOL = 1e-9 days, in the direction that keeps the event
(floor(U + TOL), ceil(U - TOL)); the registered promise in e1_models.promise uses the same 1e-9.
"""
from __future__ import annotations

import numpy as np

TOL = 1e-9
RULES = ("ceil", "floor", "minus_one")


def _finite(a) -> np.ndarray:
    a = np.asarray(a, dtype=float)
    if not np.all(np.isfinite(a)):
        raise ValueError("non-finite value")
    return a


def _vector(a, name: str) -> np.ndarray:
    a = _finite(a)
    if a.ndim != 1 or len(a) == 0:
        raise ValueError(f"{name} must be a non-empty 1-d array")
    return a


def _scalar(s) -> float:
    a = np.asarray(s, dtype=float)
    if a.ndim != 0 or not np.isfinite(a):
        raise ValueError("shift must be a finite scalar")
    return float(a)


def bound(pred, s) -> np.ndarray:
    """U = pred + s, refusing empty / non-1-d / non-finite input and a sum that overflows to inf."""
    with np.errstate(over="ignore"):
        u = _vector(pred, "pred") + _scalar(s)
    if not np.all(np.isfinite(u)):
        raise ValueError("pred + shift is not finite")
    return u


def shift(y, pred, q: float) -> float:
    """s = R_(k), k = ceil((n + 1) q); refuses k > n (no finite bound), unequal lengths, non-finite values,
    and labels that are not whole numbers >= 1 (the integer-outcome contract the rounding rules rely on)."""
    y, pred = _vector(y, "labels"), _vector(pred, "pred")
    if y.shape != pred.shape:
        raise ValueError("labels and predictions must have equal length")
    if not (np.all(y == np.round(y)) and np.all(y >= 1)):
        raise ValueError("labels must be whole numbers of days >= 1")
    if not (0 < q < 1):
        raise ValueError("q must lie in (0, 1)")
    n = len(y)
    k = int(np.ceil((n + 1) * q - 1e-12))
    if not 1 <= k <= n:
        raise ValueError(f"k = {k} outside 1..{n}")
    with np.errstate(over="ignore"):
        r = y - pred
    if not np.all(np.isfinite(r)):
        raise ValueError("residuals are not finite")
    return float(np.sort(r)[k - 1])


def promise(pred, s, rule: str) -> np.ndarray:
    if rule not in RULES:
        raise ValueError(f"unknown rule {rule!r}")
    u = bound(pred, s)
    if rule == "ceil":
        d = np.ceil(u - TOL)
    elif rule == "floor":
        d = np.floor(u + TOL)
    else:
        d = np.ceil(u - 1 - TOL)
    return np.maximum(1, d)


def on_integer_boundary(pred, s, tol: float = 1e-6) -> np.ndarray:
    """Orders whose bound U lies within tol of a whole number: the only orders where floor and minus_one CAN differ
    (they still agree when the one-day minimum binds, e.g. U = 1)."""
    u = bound(pred, s)
    return np.abs(u - np.round(u)) <= tol
