"""E1 checkpoint 3: execution steps 2-6 of the pre-registered plan (config v3).

    step 2  select   F0 -> V only: linear ablation C0..C3, HGB grid D1..D8, residual diagnostics on V
    step 3  fit      every registered final run on F
    step 4  shift    one shift per (run, q) on C (n = 17,056)
    step 5  freeze   outputs/e1/freeze/FREEZE.json (+ FREEZE.sha256); written once
    step 6  score    E, once; `score()` calls `require_frozen` before any E prediction

Nothing here edits stage 7. Pure metric / verdict helpers (bottom of file) are tested on synthetic data.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from . import e1_data as D
from . import e1_freeze as Z
from . import e1_models as M
from .io import ROOT
from sklearn.exceptions import ConvergenceWarning

OUT = ROOT / "outputs" / "e1"
PKG = ROOT / "src" / "olist_analytics"
CFG_PATH = ROOT / "config" / "date_model_e1.yaml"
S7 = ROOT / "outputs" / "stage7"
MART = ROOT / "outputs" / "marts" / "orders_mart.csv"                 # tests point this at a temporary file
INPUT_ADDENDUM = "INPUT_IDENTITY_ADDENDUM.json"
Q_MAIN, Q_OLIST = 0.90, 0.9126
QS = {"0.90": Q_MAIN, "0.9126": Q_OLIST}


# ------------------------------------------------------------------ data
def load_segments():
    c = D.cfg()
    pop, history, _ = D.load()
    segs = D.segment_rows(pop, c)
    return c, history, {k: v["used"] for k, v in segs.items()}


def build(rows, history, seg, rule):
    x, _ = D.features(rows, history, seg, rule)
    return x


# ------------------------------------------------------------------ fitting with one labelled retry
class FitFailed(RuntimeError):
    pass


def fit_linear(spec, q, X, y, *, dow_categorical, target, alpha, fallback):
    """Fit once with highs; on failure or a convergence warning retry once with the registered fallback solver."""
    attempts = []
    for solver in ("highs", fallback):
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", category=ConvergenceWarning)   # solver did not succeed
                m = M.LinearModel(spec, q, dow_categorical=dow_categorical, target=target, alpha=alpha,
                                  solver=solver).fit(X, y)
            return m, {"solver": solver, "retry": solver != "highs", "attempts": attempts}
        except Exception as e:                                  # recorded, never silent
            attempts.append({"solver": solver, "error": f"{type(e).__name__}: {e}"[:300]})
    raise FitFailed(json.dumps(attempts))


def fit_hgb(spec, hgb, q, X, y, max_depth, max_iter):
    return M.HGBModel(spec, hgb, q, max_depth, max_iter).fit(X, y)


def int_loss(y, pred, q):
    """Primary selection metric: pinball on the unshifted integer promise max(1, ceil(yhat))."""
    return M.pinball(y, M.promise(M.checked(pred, len(y))), q)


# ------------------------------------------------------------------ step 2: selection on F0 / V
def _rel(new, old):
    return (old - new) / old if np.isfinite(new) and np.isfinite(old) and old > 0 else np.nan


def linear_selection(spec, lin_abl, fallback, XF0, yF0, XV, yV, q=Q_MAIN, fitter=None, keep=None):
    """C0 -> C1 -> C2 -> C3. A step is adopted only if its V integer-day pinball is >= adopt_rel (1%) lower than the
    current best; otherwise the simpler previous setting is kept. C3 first picks alpha among the registered grid for
    the current target by the global-minimum tie rule (tie set L <= (1 + tie_rel) L_min, larger alpha preferred),
    then applies the 1% rule. Failed fits keep NaN loss, are never adopted, and are reported with the error."""
    adopt, tie = lin_abl["adopt_rel"], lin_abl["tie_rel"]
    fitter = fitter or fit_linear
    log = []

    def run(name, setting):
        row = {"step": name, **setting}
        try:
            m, info = fitter(spec, q, XF0, yF0, fallback=fallback, **setting)
            pv = M.checked(m.predict(XV), len(yV), f"{name} on V")
            if keep is not None:
                keep[name] = pv
            row.update(v_pinball_int=int_loss(yV, pv, q), v_pinball_unrounded=M.pinball(yV, pv, q),
                       solver=info["solver"], fallback_retry=info["retry"],
                       status="ok (fallback solver retry)" if info["retry"] else "ok")
        except Exception as e:                                    # FitFailed, PredictionError, ...
            row.update(v_pinball_int=np.nan, v_pinball_unrounded=np.nan, solver=None, fallback_retry=None,
                       status=f"failed: {type(e).__name__}: {e}"[:400])
        log.append(row)
        return row

    def decide(row, best_loss, best_name):
        r = _rel(row["v_pinball_int"], best_loss)
        row["rel_improvement_vs_current_best"] = r
        row["compared_with"] = best_name
        if not np.isfinite(row["v_pinball_int"]):
            row["adopted"], row["decision"] = False, f"rejected: fit or prediction failed; keep {best_name}"
        elif r >= adopt - 1e-12:
            row["adopted"], row["decision"] = True, f"adopted: V loss {r:.2%} lower than {best_name} (>= {adopt:.0%})"
        else:
            row["adopted"], row["decision"] = False, f"rejected: V loss change {r:+.2%} vs {best_name} (< {adopt:.0%} lower); keep {best_name}"
        return row["adopted"]

    c0 = {"dow_categorical": False, "target": "log1p", "alpha": 0.0}
    r0 = run("C0", c0)
    if not np.isfinite(r0["v_pinball_int"]):
        r0.update(adopted=False, decision="registered setting failed: linear family not evaluable")
        return M.NOT_EVALUABLE, pd.DataFrame(log)
    r0.update(adopted=True, decision="registered starting point")
    best, best_loss, best_name = dict(c0), r0["v_pinball_int"], "C0"

    c1 = dict(best, dow_categorical=True)
    r1 = run("C1", c1)
    if decide(r1, best_loss, best_name):
        best, best_loss, best_name = c1, r1["v_pinball_int"], "C1"

    c2 = dict(best, target="days")
    r2 = run("C2", c2)
    if decide(r2, best_loss, best_name):
        best, best_loss, best_name = c2, r2["v_pinball_int"], "C2"

    grid = [float(a) for a in lin_abl["alpha_grid"][best["target"]]]
    rows3 = {a: run(f"C3 alpha={a:g}", dict(best, alpha=a)) for a in grid}
    pick, tie_set = M.select_with_ties({a: r["v_pinball_int"] for a, r in rows3.items()}, prefer=lambda a: -a, tie_rel=tie)
    if pick == M.NOT_EVALUABLE:
        for r in rows3.values():
            r.update(adopted=False, in_tie_set=False, decision=f"rejected: every alpha failed; keep {best_name}")
    else:
        lmin = min(r["v_pinball_int"] for r in rows3.values() if np.isfinite(r["v_pinball_int"]))
        for a, r in rows3.items():
            r["in_tie_set"] = a in tie_set
            r["alpha_tie_threshold"] = (1 + tie) * lmin
            if a != pick:
                why = ("failed" if not np.isfinite(r["v_pinball_int"]) else
                       "in tie set, larger alpha preferred" if a in tie_set else "outside tie set (> 1.001 x min)")
                r.update(adopted=False, decision=f"not the alpha pick ({why})")
        if decide(rows3[pick], best_loss, best_name):
            best, best_loss, best_name = dict(best, alpha=pick), rows3[pick]["v_pinball_int"], f"C3 alpha={pick:g}"
        rows3[pick]["decision"] = "alpha pick; " + rows3[pick]["decision"]
    df = pd.DataFrame(log)
    df["selected"] = df.step == best_name
    return {"name": best_name, "setting": best, "v_pinball_int": best_loss}, df


def hgb_selection(spec, hgb, XF0, yF0, XV, yV, q=Q_MAIN, fitter=None, keep=None):
    """D1..D8 = depth {2,3} x iterations {100,200,400,800}; min V integer-day pinball; tie set L <= 1.001 L_min
    (global minimum); inside it shallower, then fewer iterations. Failures recorded, never retried with other settings."""
    fitter = fitter or fit_hgb
    grid = [(d, it) for d in hgb["grid"]["max_depth"] for it in hgb["grid"]["max_iter"]]
    rows, losses = [], {}
    for i, (d, it) in enumerate(grid, 1):
        row = {"step": f"D{i}", "max_depth": d, "max_iter": it}
        try:
            pv = M.checked(fitter(spec, hgb, q, XF0, yF0, d, it).predict(XV), len(yV), f"D{i} on V")
            if keep is not None:
                keep[f"D{i}"] = pv
            row.update(v_pinball_int=int_loss(yV, pv, q), v_pinball_unrounded=M.pinball(yV, pv, q), status="ok")
        except Exception as e:
            row.update(v_pinball_int=np.nan, v_pinball_unrounded=np.nan, status=f"failed: {type(e).__name__}: {e}"[:400])
        losses[(d, it)] = row["v_pinball_int"]
        rows.append(row)
    tie_rel = Z.THRESHOLDS["ties"]["tie_rel"]
    pick, tie_set = M.select_with_ties(losses, prefer=lambda k: (k[0], k[1]), tie_rel=tie_rel)
    df = pd.DataFrame(rows)
    if pick == M.NOT_EVALUABLE:
        df["in_tie_set"], df["selected"] = False, False
        df["decision"] = "every candidate failed: HGB family not evaluable"
        return M.NOT_EVALUABLE, df
    lmin = min(v for v in losses.values() if np.isfinite(v))
    df["tie_threshold"] = (1 + tie_rel) * lmin
    df["in_tie_set"] = [(r.max_depth, r.max_iter) in tie_set for r in df.itertuples()]
    df["selected"] = [(r.max_depth, r.max_iter) == pick for r in df.itertuples()]
    def why(r):
        if r.selected:
            return ("selected: global minimum" if len(tie_set) == 1 else
                    f"selected: in tie set of {len(tie_set)}, shallowest then fewest iterations")
        if not np.isfinite(r.v_pinball_int):
            return "failed"
        return "in tie set, but deeper or more iterations" if r.in_tie_set else "outside tie set (> 1.001 x min)"
    df["decision"] = [why(r) for r in df.itertuples()]
    name = df.loc[df.selected, "step"].iloc[0]
    return {"name": name, "setting": {"max_depth": int(pick[0]), "max_iter": int(pick[1])},
            "v_pinball_int": losses[pick]}, df


def residual_diagnostics(y, promised, purchase, pred_unrounded, seller_n, min_n=500, gap_pts=3.0):
    """Coverage by group on V (unshifted integer promise). Flag = group >= min_n orders whose coverage differs
    from overall by >= gap_pts. A flag is a PROPOSAL for the owner, never an automatic change."""
    y, d = np.asarray(y), np.asarray(promised)
    cov = (y <= d)
    overall = cov.mean()
    groups = {
        "purchase month": pd.Series(purchase).dt.to_period("M").astype(str).to_numpy(),
        "predicted-duration quartile": pd.qcut(pred_unrounded, 4, labels=["Q1 shortest", "Q2", "Q3", "Q4 longest"]).astype(str),
        "seller history n": seller_group(seller_n),
    }
    rows = []
    for gname, g in groups.items():
        for lvl in pd.unique(g):
            m = np.asarray(g) == lvl
            c = cov[m].mean()
            rows.append({"grouping": gname, "group": str(lvl), "orders": int(m.sum()), "coverage": float(c),
                         "gap_pts_vs_overall": float((c - overall) * 100),
                         "flag": bool(m.sum() >= min_n and abs(c - overall) * 100 >= gap_pts - 1e-9)})
    return pd.DataFrame(rows), float(overall)


def seller_group(n):
    n = np.nan_to_num(np.asarray(n, float), nan=0.0)
    return np.where(n == 0, "0", np.where(n < 10, "1-9", ">=10"))


# ------------------------------------------------------------------ pure scoring helpers (tested)
def practical_rule(policy: dict, ref: dict, days=Z.THRESHOLDS["practical_rule"]["days"],
                   pts=Z.THRESHOLDS["practical_rule"]["coverage_pts"]) -> bool:
    """Mean promised days <= ref - 1 day AND coverage >= ref - 1 pt."""
    return bool(policy["mean_promised_days"] <= ref["mean_promised_days"] - days + 1e-9
                and policy["coverage"] >= ref["coverage"] - pts / 100 - 1e-12)


def monthly_table(y, promised, months, target) -> pd.DataFrame:
    df = pd.DataFrame({"y": np.asarray(y), "d": np.asarray(promised), "m": np.asarray(months)})
    g = df.assign(cov=df.y <= df.d).groupby("m")
    out = g.agg(orders=("cov", "size"), coverage=("cov", "mean"), mean_promised_days=("d", "mean")).reset_index()
    out["pts_vs_target"] = (out.coverage - target) * 100
    return out.rename(columns={"m": "purchase_month"})


def monthly_reliable(mt: pd.DataFrame, min_orders=Z.THRESHOLDS["monthly_reliability"]["min_orders"],
                     pts=Z.THRESHOLDS["monthly_reliability"]["max_pts_below_target"]) -> bool:
    big = mt[mt.orders >= min_orders]
    return bool((big.pts_vs_target >= -pts - 1e-9).all())


def h1_row(state_promise, reg_promise, y) -> dict:
    s, r = M.policy_score(y, state_promise), M.policy_score(y, reg_promise)
    return {"state_mean_days": s["mean_promised_days"], "state_coverage": s["coverage"],
            "reg_mean_days": r["mean_promised_days"], "reg_coverage": r["coverage"],
            "day_gap": r["mean_promised_days"] - s["mean_promised_days"], "cov_gap": r["coverage"] - s["coverage"],
            "keep": practical_rule(r, s)}


def paired_interval(diff_per_order, weeks, draws) -> tuple[float, float]:
    rep = M.bootstrap_pooled({"d": np.asarray(diff_per_order, float)}, weeks, draws)["d"]
    lo, hi = np.percentile(rep, [2.5, 97.5])
    return float(lo), float(hi)


def versus_olist(policy: dict, olist: dict) -> bool:
    """'tighter at similar reliability' (stage-7 rule, reused for M): coverage >= Olist - 1 pt AND days <= Olist - 1."""
    return practical_rule(policy, olist)


# ------------------------------------------------------------------ helpers for the stages
def save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str))


def model_path(key):
    return OUT / "models" / f"{key}.joblib"


def predict(run_key, model, X_by_rule, state):
    reg = Z.REGISTERED_RUNS[run_key]
    if reg["model"] == "state":
        return M.state_predict(model, state)
    return model.predict(X_by_rule[reg["snapshot"]])


# ------------------------------------------------------------------ run registration and entry checks
ENTRY_MODULES = ("e1_data", "e1_models", "e1_freeze", "e1_pipeline", "features", "date_policy", "io")


def entry_modules() -> dict:
    """Paths and SHA-256 of the modules this process actually imported (not what a test printed)."""
    import importlib
    out = {}
    for name in ENTRY_MODULES:
        mod = importlib.import_module(f"olist_analytics.{name}")
        out[name] = {"file": str(mod.__file__), "sha256": Z.file_sha(mod.__file__)}
    return out


def runtime_self_check() -> list[dict]:
    """The fixed behaviour, exercised inside the run process itself."""
    rows = []
    def expect_raise(name, fn, exc):
        try:
            fn()
            rows.append({"check": name, "pass": False, "detail": "no exception"})
        except exc as e:
            rows.append({"check": name, "pass": True, "detail": f"{type(e).__name__}"})
    expect_raise("policy_score refuses a NaN label", lambda: M.policy_score([np.nan, 2.0], [1.0, 2.0]), ValueError)
    expect_raise("shift refuses a NaN label", lambda: M.shift(np.r_[np.nan, np.arange(99.0)], np.zeros(100), 0.9), ValueError)
    expect_raise("pinball refuses unequal lengths", lambda: M.pinball(np.arange(3.0), [1.0], 0.9), ValueError)
    expect_raise("freeze validation refuses a record with an empty model list",
                 lambda: Z.validate_record({k: ({} if k == "fitted_model_files_sha256" else {"x": 1})
                                            for k in Z.REQUIRED + Z.EXTRA_REQUIRED}), Z.FreezeError)
    return rows


def register_run(stage: str, partitions: dict, extra: dict | None = None) -> dict:
    from .io import sha256 as fsha
    combined, files = Z.code_fingerprint(PKG)
    reg_cfg = (OUT / "PREREGISTRATION_SHA256.txt").read_text().split()[0]
    rec = {"stage": stage, "registered_at": pd.Timestamp.now(tz="UTC").isoformat(),
           "config": {"path": "config/date_model_e1.yaml", "sha256": fsha(CFG_PATH), "registered_v3_sha256": reg_cfg,
                      "unchanged_since_registration": fsha(CFG_PATH) == reg_cfg},
           "code": {"package_fingerprint_sha256": combined, "files_sha256": files},
           "entry_modules": entry_modules(), "environment": Z.environment(),
           "data": {"orders_mart_sha256": fsha(MART) if MART.exists() else None,
                    "partition_id_sha256": partitions},
           **(extra or {})}
    return rec


# ------------------------------------------------------------------ publishing (official file written last)
OFFICIAL = "selection.json"
BLOCK = Path("qa") / "RELEASE_BLOCKED.json"


def publish(stage: Path, checks: pd.DataFrame, payload: dict, official: str = OFFICIAL) -> Path:
    """Write the official result file ONLY after every check passes. On failure: block marker written, any stale
    official file removed, exception raised; the official file never exists next to a failed check."""
    from .gate import release_gate
    checks = checks.copy()
    checks["pass"] = checks.expected.astype(str) == checks.actual.astype(str)
    checks.to_csv(stage / "post_run_checks.csv", index=False)
    release_gate(checks, stage / official, blocked_path=stage / BLOCK)     # removes stage/official on failure
    save_json(stage / official, payload)
    return stage / official


def require_published(stage: Path, official: str = OFFICIAL) -> dict:
    """Downstream entry check: refuse a stage directory that is blocked, unpublished, or whose registration changed."""
    stage = Path(stage)
    if (stage / BLOCK).exists():
        raise SystemExit(f"{stage} carries a block marker ({BLOCK}); its results may not be used")
    if not (stage / official).exists():
        raise SystemExit(f"{stage}/{official} missing: the stage did not publish a result")
    out = json.loads((stage / official).read_text())
    if Z.file_sha(stage / "RUN_REGISTRATION.json") != out.get("registration_sha256"):
        raise SystemExit(f"{stage}: RUN_REGISTRATION.json changed after the result was published")
    return out


def per_order_long(order_ids, y, preds: dict, q: float) -> pd.DataFrame:
    """order_id, candidate, q, actual_days, prediction_unrounded, promise_days (unshifted)."""
    frames = [pd.DataFrame({"order_id": np.asarray(order_ids), "candidate": k, "q": q, "actual_days": y,
                            "prediction_unrounded": v, "promise_days": M.promise(v)}) for k, v in preds.items()]
    return pd.concat(frames, ignore_index=True)


def losses_from_per_order(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute every candidate's V losses from the per-order file alone (reviewer check)."""
    rows = []
    for k, g in df.groupby("candidate", sort=False):
        rows.append({"candidate": k, "v_pinball_int": M.pinball(g.actual_days, g.promise_days, g.q.iloc[0]),
                     "v_pinball_unrounded": M.pinball(g.actual_days, g.prediction_unrounded, g.q.iloc[0]),
                     "orders": len(g)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ step 2 runner
def run_select(out_name: str = "select", reproduces: str | None = None) -> dict:
    """F0 -> V only. Writes outputs/e1/<out_name>/. Touches no C or E label, prediction or metric.
    `reproduces`: name of an earlier selection directory this run must reproduce (it is never overwritten)."""
    from .gate import release_gate
    stage = OUT / out_name
    if stage.exists() and any(stage.iterdir()):
        raise SystemExit(f"{stage} exists: a selection directory is written once (use a new name for a reproduction run)")
    (stage / "qa").mkdir(parents=True, exist_ok=True)
    c, history, used = load_segments()
    manifest = pd.read_csv(OUT / "prep" / "partition_manifest.csv").set_index("segment")
    parts = {s: D.id_sha256(used[s].order_id) for s in D.SEGMENTS}

    reg = register_run(f"select (execution step 2: F0 -> V){' - reproduction of ' + reproduces if reproduces else ''}",
                       parts, {"reproduces": reproduces})
    save_json(stage / "RUN_REGISTRATION.json", reg)                 # written before any model is fitted
    self_check = runtime_self_check()
    pre = pd.DataFrame([
        {"check": "config unchanged since v3 registration", "expected": True, "actual": reg["config"]["unchanged_since_registration"]},
        *[{"check": f"partition {s} ids == checkpoint-2 manifest", "expected": manifest.loc[s, "id_sha256"], "actual": parts[s]}
          for s in D.SEGMENTS],
        *[{"check": f"entry module {n} imported from this working copy", "expected": True,
           "actual": v["file"].startswith(str(PKG))} for n, v in reg["entry_modules"].items()],
        *[{"check": f"runtime: {r['check']}", "expected": True, "actual": r["pass"]} for r in self_check],
    ])
    pre["pass"] = pre.expected.astype(str) == pre.actual.astype(str)
    pre.to_csv(stage / "pre_run_checks.csv", index=False)
    release_gate(pre, stage / OFFICIAL, blocked_path=stage / BLOCK)

    spec, abl, hgb = c["models"]["linear_registered"], c["models"]["linear_ablation"], c["models"]["hgb"]
    XF0, XV = build(used["F0"], history, "F0", "U"), build(used["V"], history, "V", "U")
    yF0, yV = D.labels(used["F0"]).to_numpy(float), D.labels(used["V"]).to_numpy(float)
    t0 = pd.Timestamp.now()
    preds = {}
    lin_pick, lin_log = linear_selection(spec, abl, spec["fallback_solver"], XF0, yF0, XV, yV, keep=preds)
    hgb_pick, hgb_log = hgb_selection(spec, hgb, XF0, yF0, XV, yV, keep=preds)

    # residual diagnostics reuse the candidate-stage predictions (no refit)
    diags = []
    for fam, pick in (("linear", lin_pick), ("HGB", hgb_pick)):
        if pick != M.NOT_EVALUABLE:
            p = preds[pick["name"]]
            d, ov = residual_diagnostics(yV, M.promise(p), used["V"].order_purchase_timestamp, p, XV.seller_hist_n_delivered)
            diags.append(d.assign(model=f"{fam} {pick['name']}", overall_v_coverage=ov))
    diag = pd.concat(diags, ignore_index=True) if diags else pd.DataFrame()

    per_order = per_order_long(used["V"].order_id, yV, preds, Q_MAIN)
    per_order.to_csv(stage / "v_predictions_per_order.csv.gz", index=False, compression="gzip")
    recomputed = losses_from_per_order(per_order).set_index("candidate")
    logged = pd.concat([lin_log.set_index("step")[["v_pinball_int"]], hgb_log.set_index("step")[["v_pinball_int"]]])
    logged = logged[np.isfinite(logged.v_pinball_int)]
    max_gap = float(np.max(np.abs(recomputed.loc[logged.index, "v_pinball_int"] - logged.v_pinball_int)))

    lin_log.to_csv(stage / "linear_ablation.csv", index=False)
    hgb_log.to_csv(stage / "hgb_grid.csv", index=False)
    diag.to_csv(stage / "residual_diagnostics_V.csv", index=False)
    combined_after, _ = Z.code_fingerprint(PKG)
    post = [
        {"check": "package code unchanged during the run", "expected": reg["code"]["package_fingerprint_sha256"], "actual": combined_after},
        {"check": "F0 rows used", "expected": int(manifest.loc["F0", "used"]), "actual": len(yF0)},
        {"check": "V rows used", "expected": int(manifest.loc["V", "used"]), "actual": len(yV)},
        {"check": "linear candidates run (C0, C1, C2, 3 alphas)", "expected": 6, "actual": len(lin_log)},
        {"check": "HGB candidates run (8)", "expected": 8, "actual": len(hgb_log)},
        {"check": "per-order file: one row per V order per successful candidate", "expected": len(yV) * len(preds),
         "actual": len(per_order)},
        {"check": "losses recomputed from the per-order file == logged (|diff| < 1e-12)", "expected": True, "actual": max_gap < 1e-12},
    ]
    comparison = None
    if reproduces:
        orig = require_published(OUT / reproduces)
        o_lin = pd.read_csv(OUT / reproduces / "linear_ablation.csv").set_index("step")
        o_hgb = pd.read_csv(OUT / reproduces / "hgb_grid.csv").set_index("step")
        both = pd.concat([o_lin[["v_pinball_int", "adopted" if "adopted" in o_lin else "selected"]].rename(columns={"adopted": "flag"}),
                          o_hgb[["v_pinball_int", "selected"]].rename(columns={"selected": "flag"})])
        new = pd.concat([lin_log.set_index("step")[["v_pinball_int", "adopted"]].rename(columns={"adopted": "flag"}),
                         hgb_log.set_index("step")[["v_pinball_int", "selected"]].rename(columns={"selected": "flag"})])
        comparison = both.join(new, lsuffix="_original", rsuffix="_reproduction")
        comparison["abs_diff"] = (comparison.v_pinball_int_original - comparison.v_pinball_int_reproduction).abs()
        comparison.to_csv(stage / "comparison_with_original.csv")
        post += [
            {"check": f"same candidates as {reproduces}", "expected": sorted(both.index), "actual": sorted(new.index)},
            {"check": f"V losses equal to {reproduces} (max |diff| < 1e-9)", "expected": True,
             "actual": bool(comparison.abs_diff.max() < 1e-9)},
            {"check": f"adopt / select flags equal to {reproduces}", "expected": True,
             "actual": bool((comparison.flag_original.astype(bool) == comparison.flag_reproduction.astype(bool)).all())},
            {"check": f"selected linear setting equal to {reproduces}", "expected": orig["linear"]["setting"], "actual": lin_pick["setting"]},
            {"check": f"selected HGB setting equal to {reproduces}", "expected": orig["hgb"]["setting"], "actual": hgb_pick["setting"]},
        ]
    out = {"linear": lin_pick, "hgb": hgb_pick, "q": Q_MAIN, "metric": "V pinball on unshifted integer promise max(1, ceil(yhat))",
           "rows": {"F0": len(yF0), "V": len(yV)}, "runtime_seconds": (pd.Timestamp.now() - t0).total_seconds(),
           "residual_flags": diag[diag.flag].to_dict(orient="records") if len(diag) else [],
           "registration_sha256": Z.file_sha(stage / "RUN_REGISTRATION.json"), "reproduces": reproduces,
           "e_or_c_touched": False}
    publish(stage, pd.DataFrame(post), out)                         # official file only after every check passes
    return {"out": out, "lin": lin_log, "hgb": hgb_log, "diag": diag, "pre": pre, "post": pd.DataFrame(post),
            "comparison": comparison}


# ================================================================== steps 3-5: fit on F, shift on C, freeze
FINAL, SCORE = "final", "score"


def load_stage7_orders() -> pd.DataFrame:
    """Stored stage-7 per-order evaluation file (R0 and the replacement reference B0); read only at scoring time."""
    return pd.read_csv(S7 / "orders" / "evaluation_promises.csv").set_index("order_id")


def state_of(X):
    return X["customer_state_reported"]


def fit_run(key, sel, c, XF, yF):
    """Fit one registered run on F. Returns (model, preprocessing record)."""
    reg = Z.REGISTERED_RUNS[key]
    spec, hgb = c["models"]["linear_registered"], c["models"]["hgb"]
    q = reg["q"]
    if reg["model"] == "state":
        m = M.state_rule(pd.Series(yF, index=XF["U"].index), state_of(XF["U"]), q, c["models"]["state_rule"]["min_state_orders"])
        return m, {"model": "state", "q": q, "min_state_orders": c["models"]["state_rule"]["min_state_orders"],
                   "quantile_method": "inverted_cdf"}
    if reg["model"] == "linear":
        setting = ({"dow_categorical": False, "target": "log1p", "alpha": 0.0} if key.startswith(("B2", "B3"))
                   else dict(sel["linear"]["setting"]))
        m, info = fit_linear(spec, q, XF[reg["snapshot"]], yF, fallback=spec["fallback_solver"], **setting)
        rec = {"model": "linear", "q": q, **setting, "solver": info["solver"], "fallback_retry": info["retry"],
               "features": spec["numeric"] + spec["categorical"]}
        if key.startswith("Cstar"):
            rec["selected_on_V"] = sel["linear"]
        return m, rec
    setting = dict(sel["hgb"]["setting"])
    m = fit_hgb(spec, hgb, q, XF[reg["snapshot"]], yF, **setting)
    return m, {"model": "hgb", "q": q, **setting, **hgb["fixed"], "categorical": hgb["categorical"],
               "selected_on_V": sel["hgb"]}


def predict_run(key, model, X_by_rule):
    reg = Z.REGISTERED_RUNS[key]
    if reg["model"] == "state":
        return M.state_predict(model, state_of(X_by_rule["U"]))
    return model.predict(X_by_rule[reg["snapshot"]])


REF_COLS = ["required_days", "Olist_promise", "B0_state_quantile_0.90", "Q2_qr_conformal_A_0.90"]


def input_identity(used: dict, history, reference) -> dict:
    """Content hashes of every input the scoring path reads: all fields of the used rows per segment, the seller
    history the features are built from, and the stage-7 reference columns used for R0, B0 and Olist."""
    out = {f"rows_{s}": Z.canonical_frame_sha(used[s]) for s in D.SEGMENTS}
    out["seller_history"] = Z.canonical_frame_sha(history) if history is not None else Z.canonical_frame_sha(pd.DataFrame({"order_id": []}))
    out["stage7_reference"] = Z.canonical_frame_sha(reference[REF_COLS])
    return out


def run_fit_freeze(select_dir: str = "select") -> dict:
    """Steps 3-5. E is never used for fitting, calibration, selection or any metric. E is read only for integrity:
    its order ids (partition hash) and, since the post-hoc hardening, a content hash of its rows and of the stage-7
    reference columns. Hashing for identity computes nothing from E's values."""
    from .gate import release_gate
    stage = OUT / FINAL
    if stage.exists() and any(stage.iterdir()):
        raise SystemExit(f"{stage} exists: fit / freeze is run once")
    (stage / "qa").mkdir(parents=True, exist_ok=True)
    sel = require_published(OUT / select_dir)
    c, history, used = load_segments()
    manifest = pd.read_csv(OUT / "prep" / "partition_manifest.csv").set_index("segment")
    parts = {s: D.id_sha256(used[s].order_id) for s in D.SEGMENTS}
    reg = register_run("fit on F, shift on C, freeze (execution steps 3-5)", parts, {"selection_from": select_dir})
    save_json(stage / "RUN_REGISTRATION.json", reg)
    pre = pd.DataFrame([
        {"check": "config unchanged since v3 registration", "expected": True, "actual": reg["config"]["unchanged_since_registration"]},
        *[{"check": f"partition {s} ids == checkpoint-2 manifest", "expected": manifest.loc[s, "id_sha256"], "actual": parts[s]}
          for s in D.SEGMENTS],
        *[{"check": f"entry module {n} imported from this working copy", "expected": True, "actual": v["file"].startswith(str(PKG))}
          for n, v in reg["entry_modules"].items()],
        *[{"check": f"runtime: {r['check']}", "expected": True, "actual": r["pass"]} for r in runtime_self_check()],
        {"check": "no freeze record exists yet", "expected": False, "actual": (OUT / "freeze" / "FREEZE.json").exists()},
    ])
    pre["pass"] = pre.expected.astype(str) == pre.actual.astype(str)
    pre.to_csv(stage / "pre_run_checks.csv", index=False)
    release_gate(pre, stage / "FIT_SUMMARY.json", blocked_path=stage / BLOCK)

    XF = {r: build(used["F"], history, "F", r) for r in ("U", "O")}
    XC = {r: build(used["C"], history, "C", r) for r in ("U", "O")}
    yF, yC = D.labels(used["F"]).to_numpy(float), D.labels(used["C"]).to_numpy(float)
    (stage.parent / "models").mkdir(parents=True, exist_ok=True)
    runs, feats, prep, files, shifts, cpred = {}, {}, {}, {}, {}, {}
    for key, regr in Z.REGISTERED_RUNS.items():
        try:
            m, pp = fit_run(key, sel, c, XF, yF)
            pc = M.checked(predict_run(key, m, XC), len(yC), f"{key} on C")
        except Exception as e:                                         # recorded; never a silent substitute
            runs[key] = {"status": "failed", "reason": f"{type(e).__name__}: {e}"[:400]}
            continue
        path = model_path(key)
        joblib.dump(m, path)
        runs[key] = {"status": "frozen"}
        lin = c["models"]["linear_registered"]
        feats[key] = {"snapshot": regr["snapshot"],
                      "features": [] if regr["model"] == "state" else lin["numeric"] + lin["categorical"],
                      "label_rule": "only orders delivered before the snapshot contribute seller-history labels"}
        prep[key] = pp
        files[key] = {"path": str(path.relative_to(OUT)), "sha256": Z.file_sha(path)}       # relative to outputs/e1
        cpred[key] = pc
        if regr["shifted"]:
            s = M.shift(yC, pc, regr["q"])
            shifts[key] = {"n": int(len(yC)), "k": int(np.ceil((len(yC) + 1) * regr["q"])), "shift_days": float(s)}
    combined, code_files = Z.code_fingerprint(PKG)
    record = {"config_sha256": reg["config"]["sha256"], "partition_id_sha256": parts, "runs": runs,
              "feature_rules": feats, "preprocessing_and_selected_hyperparameters": prep,
              "fitted_model_files_sha256": files, "shifts_by_policy_and_q": shifts,
              "scoring_code_sha256": combined, "code_files_sha256": code_files,
              "thresholds": dict(Z.THRESHOLDS), "environment": Z.environment(),
              "input_identity": input_identity(used, history, load_stage7_orders().loc[used["E"].order_id]),
              "frozen_at": pd.Timestamp.now(tz="UTC").isoformat(), "selection_from": select_dir,
              "selection_registration_sha256": sel["registration_sha256"]}

    pd.DataFrame([{"order_id": oid, "run": k, "actual_days": y, "prediction_unrounded": p}
                  for k, v in cpred.items() for oid, y, p in zip(used["C"].order_id, yC, v)]) \
        .to_csv(stage / "c_predictions_per_order.csv.gz", index=False, compression="gzip")
    stored_shift = float(pd.read_csv(S7 / "conformal_shifts.csv").query("target == '0.90' and calibration == 'A'").shift_days.iloc[0]) \
        if (S7 / "conformal_shifts.csv").exists() else None
    same_c = ("Cstar@0.90" in cpred and "B3@0.90" in cpred
              and float(np.max(np.abs(cpred["Cstar@0.90"] - cpred["B3@0.90"]))) < 1e-9)
    post = [
        {"check": "every registered run is frozen or failed with a reason", "expected": sorted(Z.REGISTERED_RUNS), "actual": sorted(runs)},
        {"check": "calibration n == C rows used", "expected": int(manifest.loc["C", "used"]), "actual": int(len(yC))},
        {"check": "package code unchanged during the run", "expected": reg["code"]["package_fingerprint_sha256"], "actual": combined},
    ]
    if sel["linear"] != M.NOT_EVALUABLE and sel["linear"]["name"] == "C0":
        post.append({"check": "C* = C0: C* and B3 predictions identical on C (|diff| < 1e-9)", "expected": True, "actual": same_c})
    if stored_shift is not None and "B2@0.90" in shifts:
        post.append({"check": "B2 shift on C == stage-7 calibration-A shift (|diff| < 1e-6)", "expected": True,
                     "actual": abs(shifts["B2@0.90"]["shift_days"] - stored_shift) < 1e-6})
    checks = pd.DataFrame(post)
    checks["pass"] = checks.expected.astype(str) == checks.actual.astype(str)
    checks.to_csv(stage / "post_run_checks.csv", index=False)
    release_gate(checks, stage / "FIT_SUMMARY.json", blocked_path=stage / BLOCK)
    sha = Z.write_freeze(OUT / "freeze" / "FREEZE.json", record)        # validated; written once; FREEZE.sha256 beside it
    summary = {"freeze_sha256": sha, "runs": runs, "shifts": shifts, "registration_sha256": Z.file_sha(stage / "RUN_REGISTRATION.json"),
               "e_used_for_fit_calibration_selection_or_metrics": False, "e_content_hashed_for_integrity": True,
               "cstar_equals_b3_on_C": same_c}
    save_json(stage / "FIT_SUMMARY.json", summary)
    return {"summary": summary, "record": record, "checks": checks}


# ================================================================== step 6: score E once
def run_score() -> dict:
    """E, once. `require_frozen` (with the C shifts RECOMPUTED from the frozen model files) runs before any E feature,
    label or prediction is built; any failure stops here with nothing written but the registration and block marker."""
    from .gate import release_gate
    stage = OUT / SCORE
    if stage.exists() and any(stage.iterdir()):
        raise SystemExit(f"{stage} exists: E is scored once")
    (stage / "qa").mkdir(parents=True, exist_ok=True)
    c, history, used = load_segments()
    manifest = pd.read_csv(OUT / "prep" / "partition_manifest.csv").set_index("segment")
    parts_ids = {s: used[s].order_id for s in D.SEGMENTS}
    reg = register_run("score E once (execution step 6)", {s: D.id_sha256(v) for s, v in parts_ids.items()})
    save_json(stage / "RUN_REGISTRATION.json", reg)
    pre = pd.DataFrame([
        *[{"check": f"entry module {n} imported from this working copy", "expected": True, "actual": v["file"].startswith(str(PKG))}
          for n, v in reg["entry_modules"].items()],
        *[{"check": f"runtime: {r['check']}", "expected": True, "actual": r["pass"]} for r in runtime_self_check()],
    ])
    pre["pass"] = pre.expected.astype(str) == pre.actual.astype(str)
    pre.to_csv(stage / "pre_run_checks.csv", index=False)
    release_gate(pre, stage / "results.json", blocked_path=stage / BLOCK)

    XC = {r: build(used["C"], history, "C", r) for r in ("U", "O")}
    yC = D.labels(used["C"]).to_numpy(float)
    frozen = json.loads((OUT / "freeze" / "FREEZE.json").read_text()) if (OUT / "freeze" / "FREEZE.json").exists() else {}
    calls = []

    def recompute(key):                                                # mandatory: shift from the frozen file on C
        calls.append(key)
        m = joblib.load(OUT / frozen["fitted_model_files_sha256"][key]["path"])
        return M.shift(yC, M.checked(predict_run(key, m, XC), len(yC), key), Z.REGISTERED_RUNS[key]["q"])

    try:
        rec = Z.require_frozen(OUT / "freeze" / "FREEZE.json", OUT, CFG_PATH,
                               registered_config_sha=(OUT / "PREREGISTRATION_SHA256.txt").read_text().split()[0],
                               partition_ids=parts_ids, pkg_dir=PKG, recompute_shift=recompute)
    except Z.FreezeError as e:
        save_json(stage / BLOCK, [{"check": "require_frozen", "pass": False, "detail": str(e)}])
        raise
    try:
        expected_inputs = rec.get("input_identity")
        if expected_inputs is None and (OUT / "freeze" / INPUT_ADDENDUM).exists():
            expected_inputs = read_bound_addendum(OUT / "freeze" / INPUT_ADDENDUM, OUT / "freeze" / "FREEZE.json")
        if expected_inputs is None:
            raise Z.FreezeError("no input identity (freeze record or post-hoc addendum): input content cannot be checked")
        Z.require_inputs(expected_inputs, input_identity(used, history, load_stage7_orders().loc[used["E"].order_id]))
    except Z.FreezeError as e:
        save_json(stage / BLOCK, [{"check": "require_inputs", "pass": False, "detail": str(e)}])
        raise
    expected_calls = sorted(k for k, v in rec["runs"].items() if v["status"] == "frozen" and Z.REGISTERED_RUNS[k]["shifted"])
    if sorted(calls) != expected_calls:
        save_json(stage / BLOCK, [{"check": "every frozen shift recomputed on C", "pass": False}])
        raise Z.FreezeError("not every frozen shift was recomputed on C")

    # ---------------- E opened here, once
    XE = {r: build(used["E"], history, "E", r) for r in ("U", "O")}
    E = used["E"]
    yE = D.labels(E).to_numpy(float)
    q = Q_MAIN
    models = {k: joblib.load(OUT / rec["fitted_model_files_sha256"][k]["path"])
              for k, v in rec["runs"].items() if v["status"] == "frozen"}
    pred = {k: M.checked(predict_run(k, m, XE), len(yE), f"{k} on E") for k, m in models.items()}
    sh = {k: rec["shifts_by_policy_and_q"][k]["shift_days"] for k in rec["shifts_by_policy_and_q"]}
    prom = {k: M.promise(p, sh.get(k, 0.0)) for k, p in pred.items()}
    unsh = {k: M.promise(p) for k, p in pred.items()}
    s7 = load_stage7_orders().loc[E.order_id]
    month = E.order_purchase_timestamp.dt.to_period("M").astype(str).to_numpy()
    weeks = M.week_index(E.order_purchase_timestamp)
    seller = seller_group(XE["U"].seller_hist_n_delivered)
    state = state_of(XE["U"]).to_numpy()
    olist = s7["Olist_promise"].to_numpy()
    ref_b0 = s7["B0_state_quantile_0.90"].to_numpy()
    r0_reg = s7["Q2_qr_conformal_A_0.90"].to_numpy()

    po = pd.DataFrame({"order_id": E.order_id.to_numpy(), "purchase_month": month, "purchase_week_index": weeks,
                       "customer_state": state, "seller_history_n_group": seller, "actual_days": yE,
                       "stage7_B0_promise": ref_b0, "stage7_Q2A_promise": r0_reg, "olist_promise": olist})
    for k in pred:
        po[f"{k}|pred"] = pred[k]; po[f"{k}|promise_unshifted"] = unsh[k]; po[f"{k}|promise"] = prom[k]
    po.to_csv(stage / "e_promises_per_order.csv.gz", index=False, compression="gzip")

    # ---------------- policy table
    pol = {f"{k} (shifted)" if Z.REGISTERED_RUNS[k]["shifted"] else k: (prom[k], Z.REGISTERED_RUNS[k]["q"]) for k in prom}
    for k in ("B3@0.90", "Cstar@0.90", "Dstar@0.90"):
        if k in unsh:
            pol[f"{k} (unshifted)"] = (unsh[k], 0.90)
    pol["replacement reference: stage-7 B0 (F + C, no shift)"] = (ref_b0, 0.90)
    pol["R0 regression: stage-7 Q2 calibration A"] = (r0_reg, 0.90)
    pol["Olist promise"] = (olist, Q_OLIST)
    rows = []
    for name, (d, qq) in pol.items():
        rows.append({"policy": name, "q": qq, **M.policy_score(yE, d), "pinball_int": M.pinball(yE, d, qq)})
    policy = pd.DataFrame(rows)
    policy.to_csv(stage / "policy_table.csv", index=False)
    pt = policy.set_index("policy")

    monthly = pd.concat([monthly_table(yE, d, month, qq).assign(policy=name) for name, (d, qq) in pol.items()])
    monthly.to_csv(stage / "monthly.csv", index=False)
    groups = []
    for gname, g in (("customer state", state), ("seller history n", seller)):
        vc = pd.Series(g).value_counts()
        for lvl in vc[vc >= (300 if gname == "customer state" else 0)].index:
            m_ = np.asarray(g) == lvl
            for name, (d, qq) in pol.items():
                sc = M.policy_score(yE[m_], np.asarray(d)[m_])
                groups.append({"grouping": gname, "group": lvl, "orders": int(m_.sum()), "policy": name,
                               "coverage": sc["coverage"], "mean_promised_days": sc["mean_promised_days"]})
    pd.DataFrame(groups).to_csv(stage / "groups.csv", index=False)

    # ---------------- bootstrap (same draws for everything)
    rng = np.random.default_rng(Z.THRESHOLDS["bootstrap"]["seed"])
    nw = int(weeks.max()) + 1
    draws = {"iid": M.week_draws(nw, Z.THRESHOLDS["bootstrap"]["replicates"], rng, "iid"),
             "moving2": M.week_draws(nw, Z.THRESHOLDS["bootstrap"]["replicates"], rng, "moving", 2)}
    pd.DataFrame([(sch, r, j, int(w)) for sch, D_ in draws.items() for r, row in enumerate(D_) for j, w in enumerate(row)],
                 columns=["scheme", "replicate", "position", "week_index"]).to_csv(stage / "bootstrap_draws.csv.gz", index=False, compression="gzip")

    def ci(diff):
        return {sch: paired_interval(diff, weeks, D_) for sch, D_ in draws.items()}

    out = {"evaluation_orders": int(len(yE)), "weeks": nw, "not_evaluable_runs": Z.not_evaluable_runs(rec),
           "freeze_sha256": Z.file_sha(OUT / "freeze" / "FREEZE.json"), "shifts_recomputed_on_C": sorted(calls)}
    # consistency checks after opening E
    cons = {"B2 shifted promises == stored stage-7 Q2A per order": bool((prom.get("B2@0.90", r0_reg * 0) == r0_reg).all()) if "B2@0.90" in prom else None,
            "C* and B3 predictions identical on E": (bool(np.max(np.abs(pred["Cstar@0.90"] - pred["B3@0.90"])) < 1e-9)
                                                     if {"Cstar@0.90", "B3@0.90"} <= set(pred) else None)}
    out["consistency"] = cons

    # ---------------- H1 (R3 vs R0; R1, R2 descriptive)
    def row_or_none(state_p, reg_p):
        return h1_row(state_p, reg_p, yE) if state_p is not None and reg_p is not None else None
    steps = {"R0": row_or_none(ref_b0, r0_reg),
             "R1": row_or_none(prom.get("B1@0.90"), prom.get("B2@0.90")),
             "R2": row_or_none(prom.get("B1c@0.90"), prom.get("B2@0.90")),
             "R3": row_or_none(prom.get("B1c@0.90"), prom.get("B3@0.90"))}
    h1_steps, prev = [], None
    for nm, r in steps.items():
        rr = {"step": nm, **(r or {"status": M.NOT_EVALUABLE})}
        if r and prev:
            rr["change_day_gap_vs_previous"] = r["day_gap"] - prev["day_gap"]
            rr["change_cov_gap_pts_vs_previous"] = (r["cov_gap"] - prev["cov_gap"]) * 100
        h1_steps.append(rr); prev = r or prev
    pd.DataFrame(h1_steps).to_csv(stage / "h1_steps.csv", index=False)
    out["H1"] = M.h1_verdict(steps["R0"] or {}, steps["R3"] or {})

    # ---------------- H2 (C* vs B3, unshifted, integer days)
    if {"Cstar@0.90", "B3@0.90"} <= set(unsh):
        lb = M.pinball_per_order(yE, unsh["B3@0.90"], q); lc = M.pinball_per_order(yE, unsh["Cstar@0.90"], q)
        iv = ci(lc - lb)
        out["H2"] = {**M.h2_outcome(lb.mean(), lc.mean(), iv["iid"][1], sel_is_c0(rec)),
                     "L_B3": float(lb.mean()), "L_Cstar": float(lc.mean()), "delta_ci95": iv}
    else:
        out["H2"] = {"status": M.NOT_EVALUABLE}

    # ---------------- H3 and the replacement question
    def compare(a_name, a, b_name, b, target=0.90):
        pa, pb = M.policy_score(yE, a), M.policy_score(yE, b)
        mt = monthly_table(yE, a, month, target)
        cov_d = ((yE <= a).astype(float) - (yE <= b).astype(float)) * 100
        day_d = np.asarray(a, float) - np.asarray(b, float)
        return {"policy": a_name, "reference": b_name, "days_policy": pa["mean_promised_days"], "days_ref": pb["mean_promised_days"],
                "coverage_policy": pa["coverage"], "coverage_ref": pb["coverage"],
                "day_diff": pa["mean_promised_days"] - pb["mean_promised_days"],
                "coverage_diff_pts": (pa["coverage"] - pb["coverage"]) * 100,
                "practical_rule": practical_rule(pa, pb), "monthly_reliable": monthly_reliable(mt),
                "day_diff_ci95": ci(day_d), "coverage_diff_pts_ci95": ci(cov_d)}
    comps = []
    for k in ("Dstar@0.90", "Cstar@0.90"):
        if k in prom:
            if "B1c@0.90" in prom:
                comps.append(compare(f"{k} (shifted)", prom[k], "fair: B1c@0.90", prom["B1c@0.90"]))
            comps.append(compare(f"{k} (shifted)", prom[k], "replacement: stage-7 B0", ref_b0))
    save_json(stage / "comparisons.json", comps)
    h3 = next((x for x in comps if x["policy"].startswith("Dstar") and x["reference"].startswith("fair")), None)
    rep = next((x for x in comps if x["policy"].startswith("Dstar") and x["reference"].startswith("replacement")), None)
    out["H3"] = ({"status": M.NOT_EVALUABLE} if h3 is None else
                 {"status": "supported" if (h3["practical_rule"] and h3["monthly_reliable"]) else "not supported",
                  "practical_rule_vs_B1c": h3["practical_rule"], "monthly_reliable": h3["monthly_reliable"],
                  "replace_existing": bool(rep and rep["practical_rule"] and rep["monthly_reliable"])})

    # ---------------- M: q = 0.9126 vs Olist promise
    po_ = M.policy_score(yE, olist)
    out["M_vs_olist"] = [{"policy": k, **{x: M.policy_score(yE, prom[k])[x] for x in ("coverage", "mean_promised_days")},
                          "olist_coverage": po_["coverage"], "olist_mean_days": po_["mean_promised_days"],
                          "tighter_at_similar_reliability": versus_olist(M.policy_score(yE, prom[k]), po_)}
                         for k in ("B1c@0.9126", "Cstar@0.9126", "Dstar@0.9126") if k in prom]

    out["registration_sha256"] = Z.file_sha(stage / "RUN_REGISTRATION.json")
    combined_after, _ = Z.code_fingerprint(PKG)
    post = pd.DataFrame([
        {"check": "E rows == checkpoint-2 manifest", "expected": int(manifest.loc["E", "used"]), "actual": int(len(yE))},
        {"check": "package code unchanged during scoring", "expected": rec["scoring_code_sha256"], "actual": combined_after},
        *[{"check": f"consistency: {k}", "expected": True, "actual": v} for k, v in cons.items() if v is not None],
    ])
    publish(stage, post, out, official="results.json")
    return out


def sel_is_c0(rec) -> bool:
    s = rec["preprocessing_and_selected_hyperparameters"].get("Cstar@0.90", {}).get("selected_on_V", {})
    return s.get("name") == "C0"


def read_bound_addendum(path, freeze_path) -> dict:
    """The post-hoc addendum counts only if it is well-formed AND bound to this exact freeze record:
    applies_to_freeze_sha256 must equal the actual SHA-256 of FREEZE.json. Returns its input identity."""
    try:
        doc = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        raise Z.FreezeError(f"input-identity addendum unreadable: {type(e).__name__}") from e
    if not isinstance(doc, dict):
        raise Z.FreezeError("input-identity addendum is not an object")
    missing = [k for k in ("applies_to_freeze_sha256", "input_identity", "post_hoc") if k not in doc]
    if missing:
        raise Z.FreezeError(f"input-identity addendum incomplete: {missing}")
    Z._hex(doc["applies_to_freeze_sha256"], "addendum applies_to_freeze_sha256")
    if doc["applies_to_freeze_sha256"] != Z.file_sha(freeze_path):
        raise Z.FreezeError("input-identity addendum is bound to a different freeze record")
    if not isinstance(doc["input_identity"], dict):
        raise Z.FreezeError("input-identity addendum: input_identity is not an object")
    return doc["input_identity"]


def write_input_addendum() -> dict:
    """POST-HOC hardening for the E1 freeze written on 2026-10-20 (which predates input-content hashing). The old
    FREEZE.json is not touched. The addendum records the content hashes of the inputs as they are now, after
    checking that those inputs equal what was actually scored (labels and references in the saved per-order files)."""
    path = OUT / "freeze" / INPUT_ADDENDUM
    if path.exists():
        raise SystemExit(f"{path} exists: written once")
    c, history, used = load_segments()
    ref = load_stage7_orders().loc[used["E"].order_id]
    scored = pd.read_csv(OUT / SCORE / "e_promises_per_order.csv.gz").set_index("order_id").loc[used["E"].order_id]
    cpo = pd.read_csv(OUT / FINAL / "c_predictions_per_order.csv.gz")
    c_scored = cpo[cpo.run == cpo.run.iloc[0]].set_index("order_id").loc[used["C"].order_id]
    checks = {
        "E labels now == labels in the scored per-order file": bool((D.labels(used["E"]).to_numpy() == scored.actual_days.to_numpy()).all()),
        "stage-7 B0 now == B0 in the scored per-order file": bool((ref["B0_state_quantile_0.90"].to_numpy() == scored.stage7_B0_promise.to_numpy()).all()),
        "stage-7 Q2A now == Q2A in the scored per-order file": bool((ref["Q2_qr_conformal_A_0.90"].to_numpy() == scored.stage7_Q2A_promise.to_numpy()).all()),
        "Olist promise now == Olist promise in the scored per-order file": bool((ref["Olist_promise"].to_numpy() == scored.olist_promise.to_numpy()).all()),
        "C labels now == labels in the saved C predictions": bool((D.labels(used["C"]).to_numpy() == c_scored.actual_days.to_numpy()).all()),
    }
    if not all(checks.values()):
        raise SystemExit(f"inputs differ from what was scored: {checks}")
    rec = {"written_at": pd.Timestamp.now(tz="UTC").isoformat(), "post_hoc": True,
           "applies_to_freeze_sha256": Z.file_sha(OUT / "freeze" / "FREEZE.json"),
           "note": "written AFTER the E1 scoring; the original freeze did not hash input content; FREEZE.json unchanged",
           "checks_before_writing": checks, "input_identity": input_identity(used, history, ref)}
    save_json(path, rec)
    return rec
