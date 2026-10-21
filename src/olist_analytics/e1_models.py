"""E1 model layer: state rule, linear quantile variants, shallow HGB, one-sided shift, pinball loss, week bootstrap.

Library code used as is: scikit-learn (QuantileRegressor, HistGradientBoostingRegressor, preprocessing),
numpy, pandas. Stage-7 helpers are imported unchanged from `date_policy.py`.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import QuantileRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, OrdinalEncoder, StandardScaler

from .date_policy import apply_state_policy, conformal_shift, state_quantile_policy, to_promise
from .e1_freeze import THRESHOLDS


# ------------------------------------------------------------------ input checks (stop, never drop rows)
class InputError(ValueError):
    pass


def check_q(q) -> float:
    if isinstance(q, bool) or not isinstance(q, (int, float, np.floating)) or not (0 < float(q) < 1):
        raise InputError(f"q must be a number with 0 < q < 1, got {q!r}")
    return float(q)


def check_pair(y, pred, what: str) -> tuple[np.ndarray, np.ndarray]:
    """Labels and predictions: 1-D, same length, non-empty, all finite. Raises; never drops or repairs rows."""
    try:
        a, b = np.asarray(y, float), np.asarray(pred, float)
    except (TypeError, ValueError) as e:
        raise InputError(f"{what}: not numeric ({e})") from e
    if a.ndim != 1 or b.ndim != 1:
        raise InputError(f"{what}: labels and predictions must be 1-D (got {a.ndim}-D and {b.ndim}-D)")
    if len(a) == 0:
        raise InputError(f"{what}: empty input")
    if len(a) != len(b):
        raise InputError(f"{what}: {len(a)} labels but {len(b)} predictions")
    for name, v in (("labels", a), ("predictions", b)):
        bad = ~np.isfinite(v)
        if bad.any():
            raise InputError(f"{what}: {int(bad.sum())} non-finite {name}")
    return a, b


# ------------------------------------------------------------------ metrics
def pinball(y, pred, q: float) -> float:
    """Mean pinball (quantile) loss in days: q*u if u >= 0 else (q-1)*u, u = y - pred."""
    return float(np.mean(pinball_per_order(y, pred, q)))


def pinball_per_order(y, pred, q: float) -> np.ndarray:
    q = check_q(q)
    a, b = check_pair(y, pred, "pinball")
    u = a - b
    return np.maximum(q * u, (q - 1) * u)


def policy_score(y, promised) -> dict:
    y, d = check_pair(y, promised, "policy score")
    miss = y > d
    return {"orders": int(len(y)), "coverage": float((~miss).mean()), "mean_promised_days": float(d.mean()),
            "median_promised_days": float(np.median(d)), "n_missed": int(miss.sum()),
            "mean_overrun_days_when_missed": float((y - d)[miss].mean()) if miss.any() else 0.0}


# ------------------------------------------------------------------ predictions must cover every row
class PredictionError(ValueError):
    pass


def checked(pred, n_rows: int, what: str = "prediction") -> np.ndarray:
    """No silent drops: a prediction for every row, all finite, on the day scale."""
    p = np.asarray(pred, float)
    if p.shape != (n_rows,):
        raise PredictionError(f"{what}: {p.shape[0] if p.ndim else 0} values for {n_rows} rows")
    if not np.isfinite(p).all():
        raise PredictionError(f"{what}: {int((~np.isfinite(p)).sum())} non-finite values")
    return p


# ------------------------------------------------------------------ calibration (one-sided shift, one interface)
def shift(cal_y, cal_pred_unrounded, q: float) -> float:
    """Delta = s_(k), s_i = y_i - yhat_i (day scale, unrounded), k = ceil((n+1) q). May be negative.
    Raises when k > n (no finite shift exists) or on non-finite input; never falls back to 0."""
    q = check_q(q)
    y, pred = check_pair(cal_y, cal_pred_unrounded, "calibration")
    s = conformal_shift(y, pred, q)
    if not np.isfinite(s):
        raise PredictionError(f"no finite shift: k = ceil((n+1)q) > n for n = {len(y)}, q = {q}")
    return float(s)


def promise(pred_unrounded, s: float = 0.0) -> np.ndarray:
    """d(x) = max(1, ceil(yhat(x) + s)), with ceil(x - 1e-9) so float noise cannot add a day."""
    p = np.asarray(pred_unrounded, float)
    if p.ndim != 1 or len(p) == 0:
        raise InputError("promise: predictions must be a non-empty 1-D array")
    if isinstance(s, bool) or not np.isfinite(s):
        raise InputError(f"promise: shift must be finite, got {s!r}")
    return to_promise(checked(p, len(p)) + s)


# ------------------------------------------------------------------ state rule
def state_rule(train_y: pd.Series, train_state: pd.Series, q: float, min_n: int) -> dict:
    return state_quantile_policy(train_y, train_state, q, min_n)          # inverted_cdf since v0.6.1


def state_predict(policy: dict, state: pd.Series) -> np.ndarray:
    return apply_state_policy(policy, state).to_numpy().astype(float)


# ------------------------------------------------------------------ linear quantile regression
def _log1p(x):
    return np.log1p(np.clip(x, 0, None))


def linear_pipeline(spec: dict, q: float, *, dow_categorical: bool = False, target: str = "log1p",
                    alpha: float = 0.0, solver: str = "highs") -> Pipeline:
    numeric = [c for c in spec["numeric"] if not (dow_categorical and c == "purchase_dow")]
    categorical = spec["categorical"] + (["purchase_dow"] if dow_categorical else [])
    logged = [c for c in numeric if c in spec["log_transform"]]
    plain = [c for c in numeric if c not in spec["log_transform"]]
    pre = ColumnTransformer([
        ("log", Pipeline([("imp", SimpleImputer(strategy="median", add_indicator=True)),
                          ("log", FunctionTransformer(_log1p, feature_names_out="one-to-one")),
                          ("sc", StandardScaler())]), logged),
        ("num", Pipeline([("imp", SimpleImputer(strategy="median", add_indicator=True)), ("sc", StandardScaler())]), plain),
        ("cat", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=spec["categorical_min_count"]), categorical),
    ])
    pipe = Pipeline([("pre", pre), ("qr", QuantileRegressor(quantile=q, alpha=alpha, solver=solver))])
    pipe.target_ = target
    return pipe


class LinearModel:
    """Fits on the target scale named in `target` ('log1p' or 'days'); predicts unrounded days."""

    def __init__(self, spec, q, **kw):
        self.target = kw.get("target", "log1p")
        self.pipe = linear_pipeline(spec, q, **kw)
        self.cols = spec["numeric"] + spec["categorical"]

    def fit(self, X: pd.DataFrame, y_days):
        y = np.log1p(np.asarray(y_days, float)) if self.target == "log1p" else np.asarray(y_days, float)
        self.pipe.fit(X[self.cols], y)
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        p = self.pipe.predict(X[self.cols])
        return np.expm1(p) if self.target == "log1p" else p


# ------------------------------------------------------------------ shallow HGB
class HGBModel:
    """HistGradientBoostingRegressor(loss='quantile') on raw days; categories ordinal-encoded on training rows only."""

    def __init__(self, spec: dict, hgb: dict, q: float, max_depth: int, max_iter: int):
        self.num = [c for c in spec["numeric"] if c not in hgb["categorical"]]
        self.cat = list(hgb["categorical"])
        self.enc = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1, encoded_missing_value=-1)
        self.model = HistGradientBoostingRegressor(loss="quantile", quantile=q, max_depth=max_depth, max_iter=max_iter,
                                                   categorical_features=list(range(len(self.num), len(self.num) + len(self.cat))),
                                                   **hgb["fixed"])

    def _matrix(self, X, fit=False):
        cat = X[self.cat].astype(str)
        c = self.enc.fit_transform(cat) if fit else self.enc.transform(cat)
        c = np.where(c < 0, np.nan, c)                       # unseen category -> missing (HGB handles NaN)
        return np.column_stack([X[self.num].to_numpy(float), c])

    def fit(self, X, y_days):
        self.model.fit(self._matrix(X, fit=True), np.asarray(y_days, float))
        return self

    def predict(self, X) -> np.ndarray:
        return self.model.predict(self._matrix(X))


# ------------------------------------------------------------------ week block bootstrap
def week_index(purchase: pd.Series) -> np.ndarray:
    wk = purchase.dt.normalize() - pd.to_timedelta(purchase.dt.weekday, unit="D")
    return pd.factorize(wk, sort=True)[0]


def week_draws(n_weeks: int, reps: int, rng: np.random.Generator, scheme: str = "iid", block: int = 2) -> np.ndarray:
    """(reps, n_weeks) array of week indices. 'iid': weeks with replacement. 'moving': blocks of `block` consecutive
    weeks, starts uniform on 0..n_weeks-block (no wrap), concatenated and cut to n_weeks."""
    if scheme == "iid":
        return rng.integers(0, n_weeks, size=(reps, n_weeks))
    nb = int(np.ceil(n_weeks / block))
    starts = rng.integers(0, n_weeks - block + 1, size=(reps, nb))
    seq = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(reps, nb * block)
    return seq[:, :n_weeks]


def bootstrap_pooled(per_order: dict[str, np.ndarray], weeks: np.ndarray, draws: np.ndarray,
                     stat=np.mean) -> dict[str, np.ndarray]:
    """Same week draws for every series; each replicate pools ALL orders of the drawn weeks (a week drawn twice
    counts twice) and recomputes the per-order statistic. Returns {name: replicate values}."""
    weeks = np.asarray(weeks)
    for k, v in per_order.items():
        if np.shape(v) != weeks.shape or not np.isfinite(np.asarray(v, float)).all():
            raise InputError(f"bootstrap: series {k!r} must be finite with one value per order")
    order_lists = [np.flatnonzero(weeks == w) for w in range(weeks.max() + 1)]
    out = {k: np.empty(len(draws)) for k in per_order}
    for r, d in enumerate(draws):
        idx = np.concatenate([order_lists[w] for w in d])
        for k, v in per_order.items():
            out[k][r] = stat(v[idx])
    return out


# ------------------------------------------------------------------ selection and verdict rules (pre-registered)
NOT_EVALUABLE = "not evaluable"


def select_with_ties(losses: dict, prefer, tie_rel: float = THRESHOLDS["ties"]["tie_rel"]):
    """Pick from {candidate: V loss}. Failed candidates carry None/NaN and are skipped. The tie set is every
    candidate with L_i <= (1 + tie_rel) * L_min (global minimum, so the result does not depend on iteration order);
    `prefer` is a sort key applied inside the tie set (smaller = preferred). Returns (choice, tie_set) or
    (NOT_EVALUABLE, []) when every candidate failed."""
    ok = {k: v for k, v in losses.items() if v is not None and np.isfinite(v)}
    if not ok:
        return NOT_EVALUABLE, []
    lmin = min(ok.values())
    tie = sorted([k for k, v in ok.items() if v <= (1 + tie_rel) * lmin], key=prefer)
    return tie[0], tie


def h1_verdict(r0: dict, r3: dict, day_thr: float = THRESHOLDS["H1"]["days"],
               pt_thr: float = THRESHOLDS["H1"]["coverage_pts"]) -> dict:
    """Primary H1 judgment uses R0 and R3 only. Each dict: day_gap (regression - state, days),
    cov_gap (regression - state, coverage share), keep (practical-rule verdict). R1/R2 are descriptive."""
    vals = [r0.get("day_gap"), r0.get("cov_gap"), r3.get("day_gap"), r3.get("cov_gap")]
    if any(v is None or not np.isfinite(v) for v in vals) or r0.get("keep") is None or r3.get("keep") is None:
        return {"status": NOT_EVALUABLE}
    d_days = r3["day_gap"] - r0["day_gap"]
    d_pts = (r3["cov_gap"] - r0["cov_gap"]) * 100
    met = abs(d_days) >= day_thr - 1e-9 or abs(d_pts) >= pt_thr - 1e-9 or bool(r3["keep"]) != bool(r0["keep"])
    return {"status": "meets H1 standard" if met else "no change reaching the practical thresholds",
            "change_day_gap": d_days, "change_cov_gap_pts": d_pts, "verdict_changed": bool(r3["keep"]) != bool(r0["keep"])}


def h2_outcome(loss_b3: float, loss_cstar: float, delta_ci_upper: float, cstar_is_c0: bool,
               g_thr: float = THRESHOLDS["H2"]["relative_improvement"]) -> dict:
    """g = (L_B3 - L_C*) / L_B3 (relative improvement); delta = L_C* - L_B3 (absolute, its interval decides
    the evidence). 'No change selected' is recorded separately from the three outcomes."""
    if any(v is None or not np.isfinite(v) for v in (loss_b3, loss_cstar, delta_ci_upper)) or loss_b3 <= 0:
        return {"status": NOT_EVALUABLE}
    g = (loss_b3 - loss_cstar) / loss_b3
    if g >= g_thr - 1e-12:
        status = "meets the pre-set improvement standard" if delta_ci_upper < 0 else \
            "point estimate meets the standard; evidence insufficient"
    else:
        status = "below this project's practical standard"
    return {"status": status, "g": g, "delta": loss_cstar - loss_b3, "no_change_selected": bool(cstar_is_c0)}
