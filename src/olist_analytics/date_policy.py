"""Stage 7 building blocks: promised-date policies and how to score them.

All quantities are whole calendar days, matching the project's on-time rule exactly:
    required_days = delivered calendar day - purchase calendar day
    covered       = required_days <= promised_days
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import QuantileRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler


def required_days(m: pd.DataFrame) -> pd.Series:
    return (m.order_delivered_customer_date.dt.normalize() - m.order_purchase_timestamp.dt.normalize()).dt.days


def olist_promise_days(m: pd.DataFrame) -> pd.Series:
    return (m.order_estimated_delivery_date.dt.normalize() - m.order_purchase_timestamp.dt.normalize()).dt.days


# ------------------------------------------------------------------ policies
def state_quantile_policy(train_req: pd.Series, train_state: pd.Series, level: float, min_n: int) -> dict:
    """B0: per-state empirical quantile = the smallest whole day d with share(req <= d) >= level,
    i.e. the ceil(n * level)-th smallest value (numpy method "inverted_cdf")."""
    q = lambda s: float(np.quantile(s.to_numpy(), level, method="inverted_cdf"))
    overall = q(train_req)
    by_state = {st: q(g) for st, g in train_req.groupby(train_state) if len(g) >= min_n}
    return {"overall": overall, "by_state": by_state, "level": level}


def apply_state_policy(policy: dict, state: pd.Series) -> pd.Series:
    return state.map(policy["by_state"]).fillna(policy["overall"]).astype(int)


def quantile_regression(level: float, numeric: list[str], log_cols: list[str], categorical: list[str],
                        min_count: int) -> Pipeline:
    """Q1: linear quantile regression on log1p(required_days); preprocessing fitted on training rows only."""
    plain = [c for c in numeric if c not in log_cols]
    logged = [c for c in numeric if c in log_cols]
    log1p = FunctionTransformer(lambda x: np.log1p(np.clip(x, 0, None)), feature_names_out="one-to-one")
    pre = ColumnTransformer([
        ("log", Pipeline([("imp", SimpleImputer(strategy="median", add_indicator=True)), ("log", log1p),
                          ("sc", StandardScaler())]), logged),
        ("num", Pipeline([("imp", SimpleImputer(strategy="median", add_indicator=True)), ("sc", StandardScaler())]), plain),
        ("cat", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=min_count), categorical),
    ])
    return Pipeline([("pre", pre), ("qr", QuantileRegressor(quantile=level, alpha=0.0, solver="highs"))])


def predicted_days(model: Pipeline, X: pd.DataFrame) -> np.ndarray:
    return np.expm1(model.predict(X))


def conformal_shift(cal_required: np.ndarray, cal_predicted: np.ndarray, level: float) -> float:
    """One-sided split conformal: the ceil((n+1)*level)-th smallest score, score = required - predicted.
    Returns +inf when the calibration set is too small for the level (no finite promise is valid)."""
    scores = np.sort(np.asarray(cal_required, float) - np.asarray(cal_predicted, float))
    n = len(scores)
    k = int(np.ceil((n + 1) * level))
    return float("inf") if k > n else float(scores[k - 1])


def to_promise(days: np.ndarray, minimum: int = 1) -> np.ndarray:
    """Whole promised days. Refuses non-finite input (e.g. an infinite conformal shift: no finite promise is valid)."""
    days = np.asarray(days, float)
    if not np.isfinite(days).all():
        raise ValueError("no finite promise: non-finite predicted days (calibration set too small for the level?)")
    return np.maximum(np.ceil(np.asarray(days, float) - 1e-9), minimum).astype(int)


# ------------------------------------------------------------------ scoring
def score(required: pd.Series, promised: pd.Series) -> dict:
    req, prom = np.asarray(required), np.asarray(promised)
    miss = req > prom
    return {"orders": int(len(req)), "coverage": float((~miss).mean()), "mean_promised_days": float(prom.mean()),
            "median_promised_days": float(np.median(prom)),
            "mean_overrun_days_when_missed": float((req - prom)[miss].mean()) if miss.any() else 0.0,
            "mean_slack_days": float((prom - req).mean())}


TOL = 1e-9   # floating-point tolerance at the registered 1-day / 1-point edges


def verdict_complex_over_baseline(cx: dict, base: dict, days: float = 1.0, cov_pts: float = 1.0) -> dict:
    shorter = base["mean_promised_days"] - cx["mean_promised_days"]
    drop = (base["coverage"] - cx["coverage"]) * 100
    return {"days_shorter": shorter, "coverage_drop_pts": drop,
            "keep_complex": bool(shorter >= days - TOL and drop <= cov_pts + TOL)}


def monthly_unreliable(monthly: pd.DataFrame, target: float, min_orders: int = 1000, pts: float = 3.0) -> list[str]:
    m = monthly[monthly.orders >= min_orders]
    return [str(r.month) for r in m.itertuples() if (target - r.coverage) * 100 > pts + TOL]
