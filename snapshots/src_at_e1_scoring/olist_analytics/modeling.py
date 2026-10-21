"""Model pipelines and evaluation (stage 3). Preprocessing lives inside each Pipeline,
so it is fit on training rows only."""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, OrdinalEncoder, StandardScaler

from .features import CAT, CFG, NUM

SKEWED = ["distance_km", "items_price_sum", "items_freight_sum", "freight_ratio", "weight_g_sum",
          "seller_hist_n_delivered", "seller_hist_n_placed", "seller_hist_handling_median_h", "seller_age_days"]


def logistic(C: float, num=None, cat=None) -> Pipeline:
    num = [c for c in (num or NUM)]
    cat = [c for c in (cat or CAT)]
    skew = [c for c in num if c in SKEWED]
    plain = [c for c in num if c not in SKEWED]
    clip_log = FunctionTransformer(lambda x: np.log1p(np.clip(x, 0, None)), feature_names_out="one-to-one")
    pre = ColumnTransformer([
        ("skew", Pipeline([("imp", SimpleImputer(strategy="median", add_indicator=True)),
                           ("log", clip_log), ("sc", StandardScaler())]), skew),
        ("num", Pipeline([("imp", SimpleImputer(strategy="median", add_indicator=True)),
                          ("sc", StandardScaler())]), plain),
        ("cat", OneHotEncoder(handle_unknown="infrequent_if_exist", min_frequency=50), cat),
    ])
    return Pipeline([("pre", pre), ("clf", LogisticRegression(C=C, max_iter=3000))])


def gbm(params: dict, num=None, cat=None, seed=None) -> Pipeline:
    num = [c for c in (num or NUM)]
    cat = [c for c in (cat or CAT)]
    pre = ColumnTransformer([
        ("num", "passthrough", num),
        ("cat", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=np.nan,
                               encoded_missing_value=np.nan, min_frequency=50), cat),
    ])
    clf = HistGradientBoostingClassifier(**params, categorical_features=[False] * len(num) + [True] * len(cat),
                                         early_stopping=False, random_state=seed or CFG["models"]["seed"])
    return Pipeline([("pre", pre), ("clf", clf)])


def candidates(num=None, cat=None):
    for C in CFG["models"]["logistic_C"]:
        yield "logistic", {"C": C}, (lambda C=C: logistic(C, num, cat))
    g = CFG["models"]["gbm_grid"]
    for combo in itertools.product(*g.values()):
        p = dict(zip(g.keys(), combo))
        yield "gbm", p, (lambda p=p: gbm(p, num, cat))


# ------------------------------------------------------------------ metrics
def top_share_by_week(y, s, week, share: float) -> dict:
    """Per purchase week pick floor(share x n) highest scores (ties broken by row order)."""
    d = pd.DataFrame({"y": np.asarray(y), "s": np.asarray(s), "w": np.asarray(week)})
    sel = tp = 0
    for _, g in d.groupby("w"):
        k = int(np.floor(share * len(g)))
        if k == 0:
            continue
        top = g.sort_values("s", ascending=False, kind="mergesort").head(k)
        sel += k
        tp += int(top.y.sum())
    pos = int(d.y.sum())
    return {"selected": sel, "true_late_in_selected": tp,
            "precision_at_top": tp / sel if sel else np.nan, "recall_at_top": tp / pos if pos else np.nan}


def score_metrics(y, p, week, share) -> dict:
    y, p = np.asarray(y), np.asarray(p)
    out = {"n": int(len(y)), "late": int(y.sum()), "prevalence": float(y.mean()),
           "average_precision": float(average_precision_score(y, p)),
           "roc_auc": float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else np.nan,
           "brier": float(brier_score_loss(y, p)), "log_loss": float(log_loss(y, np.clip(p, 1e-6, 1 - 1e-6)))}
    out.update(top_share_by_week(y, p, week, share))
    return out


def calibration_table(y, p, bins: int) -> pd.DataFrame:
    d = pd.DataFrame({"y": np.asarray(y), "p": np.asarray(p)})
    d["bin"] = pd.qcut(d.p.rank(method="first"), bins, labels=False)
    t = d.groupby("bin").agg(n=("y", "size"), mean_predicted=("p", "mean"), observed_rate=("y", "mean")).reset_index()
    return t


def week_bootstrap(y, scores: dict[str, np.ndarray], week, reps: int, seed: int) -> pd.DataFrame:
    """Resample purchase weeks (not orders) to respect within-week correlation."""
    d = pd.DataFrame({"y": np.asarray(y), "w": np.asarray(week), **{k: np.asarray(v) for k, v in scores.items()}})
    groups = [g for _, g in d.groupby("w")]
    rng = np.random.default_rng(seed)
    rows = []
    for _ in range(reps):
        b = pd.concat([groups[i] for i in rng.integers(0, len(groups), len(groups))], ignore_index=True)
        if b.y.sum() == 0:
            continue
        rows.append({k: average_precision_score(b.y, b[k]) for k in scores})
    return pd.DataFrame(rows)


def importance(model, X, y, repeats: int, seed: int) -> pd.DataFrame:
    r = permutation_importance(model, X, y, scoring="average_precision", n_repeats=repeats, random_state=seed)
    return (pd.DataFrame({"feature": X.columns, "ap_drop_mean": r.importances_mean, "ap_drop_std": r.importances_std})
            .sort_values("ap_drop_mean", ascending=False).reset_index(drop=True))
