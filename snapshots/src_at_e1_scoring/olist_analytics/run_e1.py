"""E1 runner. Checkpoint 2 = stage `prep` only (execution-order step 1): no new evaluation-set metric is written.

    PYTHONPATH=src python -m olist_analytics.run_e1 prep

prep writes outputs/e1/prep/:
  segment_counts.csv, monthly_counts.csv, exclusion_steps.csv   sample tables (eligible vs used, late-rate denominators)
  feature_build.csv                                             snapshot meta per (segment, rule): labels known, max label date
  historical_reproduction.csv                                   stage-7 numbers recomputed from stored per-order files
  b2_reproduction.json                                          B2 (= stage-7 Q1) refit: max |prediction difference| only
  checks.csv, lineage.json                                      blocking checks; versions; config hash
"""
from __future__ import annotations

import json
import platform
import sys

import numpy as np
import pandas as pd

from . import e1_data as D
from . import e1_models as M
from .gate import ReleaseBlocked, release_gate as shared_release_gate
from .io import ROOT, sha256

OUT = ROOT / "outputs" / "e1"
CFG_PATH = ROOT / "config" / "date_model_e1.yaml"
S7 = ROOT / "outputs" / "stage7"


def registered_sha() -> str:
    return (OUT / "PREREGISTRATION_SHA256.txt").read_text().split()[0]


def gate(checks: pd.DataFrame, stage: str) -> None:
    shared_release_gate(checks, OUT / stage / "REPORT_PLACEHOLDER.md", blocked_path=OUT / stage / "qa" / "RELEASE_BLOCKED.json")


def versions() -> dict:
    import scipy
    import sklearn
    return {"python": sys.version.split()[0], "platform": platform.platform(), "numpy": np.__version__,
            "pandas": pd.__version__, "scikit-learn": sklearn.__version__, "scipy": scipy.__version__}


def historical_reproduction() -> pd.DataFrame:
    """Stage-7 policies at q = 0.90 from the stored per-order file (numbers already published; nothing new)."""
    d = pd.read_csv(S7 / "orders" / "evaluation_promises.csv")
    y = d.required_days.to_numpy()
    rows = []
    for col in ["B0_state_quantile_0.90", "Q1_quantile_regression_0.90", "Q2_qr_conformal_A_0.90",
                "Q2_qr_conformal_B_0.90", "Olist_promise"]:
        rows.append({"policy": col, "pinball_q090_integer_days": M.pinball(y, d[col], 0.90), **M.policy_score(y, d[col])})
    rows.append({"policy": "q_pred_days_0.90 (unrounded)", "pinball_q090_integer_days": M.pinball(y, d["q_pred_days_0.90"], 0.90)})
    return pd.DataFrame(rows)


def prep() -> dict:
    stage = OUT / "prep"
    (stage / "qa").mkdir(parents=True, exist_ok=True)
    c = D.cfg()
    pre = pd.DataFrame([
        {"check": "E1 config matches its registered SHA-256", "expected": registered_sha(), "actual": sha256(CFG_PATH)},
        {"check": "stage-7 config unchanged", "expected": c["base"]["stage7_config_sha256"],
         "actual": sha256(ROOT / "config" / "date_policy.yaml")},
    ])
    pre["pass"] = pre.expected.astype(str) == pre.actual.astype(str)
    gate(pre, "prep")

    pop, history, steps = D.load()
    segs = D.segment_rows(pop, c)
    tables = D.sample_tables(pop, segs, steps, c)
    part = D.partition_checks(segs, c)
    manifest = D.partition_manifest(segs, c)

    # feature builds: every (segment, rule) the plan needs; attach_seller raises on any future label
    builds, X = [], {}
    for seg, rule in [("F0", "U"), ("V", "U"), ("F", "U"), ("C", "U"), ("E", "U"), ("F", "O"), ("C", "O"), ("E", "O")]:
        rows = segs[seg]["used"]
        times = D.snapshot_times(rows, seg, rule)
        x, metas = D.features(rows, history, seg, rule)
        X[(seg, rule)] = x
        T = pd.to_datetime(pd.Series([m["T"] for m in metas]))
        maxlab = pd.to_datetime(pd.Series([m["max_label_delivery"] for m in metas]))
        builds.append({"segment": seg, "rule": rule, "rows": len(rows), "snapshots": len(metas),
                       "earliest_snapshot": str(T.min()), "latest_snapshot": str(T.max()),
                       "every_label_before_its_snapshot": bool((maxlab < T).all()),
                       "every_snapshot_at_or_before_purchase": bool((times <= rows.order_purchase_timestamp).all())})
    builds = pd.DataFrame(builds)

    # B2 reproduction (stage-7 Q1 refit; compares predictions only, writes no metric)
    spec = c["models"]["linear_registered"]
    yF = D.labels(segs["F"]["used"])
    b2 = M.LinearModel(spec, 0.90, target="log1p", alpha=0.0).fit(X[("F", "O")], yF)
    stored = pd.read_csv(S7 / "orders" / "evaluation_promises.csv").set_index("order_id")
    e_ids = segs["E"]["used"].order_id.to_numpy()
    pred_e = b2.predict(X[("E", "O")])
    diff_e = float(np.max(np.abs(pred_e - stored.loc[e_ids, "q_pred_days_0.90"].to_numpy())))
    yC = D.labels(segs["C"]["used"]).to_numpy()
    b2_c_pred = M.checked(b2.predict(X[("C", "O")]), len(yC), "B2 on C")
    s_b2 = M.shift(yC, b2_c_pred, 0.90)
    s_stored = float(pd.read_csv(S7 / "conformal_shifts.csv").query("target == '0.90' and calibration == 'A'").shift_days.iloc[0])
    b2rep = {"max_abs_diff_unrounded_E_prediction_days": diff_e, "C_shift_refit": s_b2, "C_shift_stored": s_stored,
             "integer_promises_identical": bool((M.promise(pred_e) == stored.loc[e_ids, "Q1_quantile_regression_0.90"].to_numpy()).all()
                                                and (M.promise(pred_e, s_b2) == stored.loc[e_ids, "Q2_qr_conformal_A_0.90"].to_numpy()).all())}

    hist = historical_reproduction()
    counts = tables["segment_counts"].set_index("segment")
    checks = pd.concat([pre, part, pd.DataFrame([
        {"check": "every feature build: labels before snapshot", "expected": True, "actual": bool(builds.every_label_before_its_snapshot.all())},
        {"check": "every feature build: snapshot at or before purchase", "expected": True, "actual": bool(builds.every_snapshot_at_or_before_purchase.all())},
        {"check": "F used == stage-7 fit set (25,666)", "expected": 25666, "actual": int(counts.loc["F", "used"])},
        {"check": "calibration n (C rows actually used) == 17,056 of 17,063 eligible", "expected": "17056/17063",
         "actual": f"{int(counts.loc['C', 'used'])}/{int(counts.loc['C', 'eligible'])}"},
        {"check": "every manifest line: eligible == used + excluded", "expected": True,
         "actual": bool((manifest.eligible == manifest.used + manifest.excluded).all())},
        {"check": "every feature build returned one row per used order", "expected": True,
         "actual": all(len(X[(sg, rl)]) == len(segs[sg]["used"]) for sg, rl in X)},
        {"check": "C used == stage-7 calibration A (17,056)", "expected": 17056, "actual": int(counts.loc["C", "used"])},
        {"check": "E used == stage-7 evaluation (19,950)", "expected": 19950, "actual": int(counts.loc["E", "used"])},
        {"check": "E order ids == stored stage-7 per-order ids", "expected": True,
         "actual": set(e_ids) == set(stored.index)},
        {"check": "B2 reproduces stage-7 Q1 predictions (max |diff| < 1e-6 day)", "expected": True, "actual": diff_e < 1e-6},
        {"check": "B2 reproduces stage-7 calibration-A shift (|diff| < 1e-6)", "expected": True, "actual": abs(s_b2 - s_stored) < 1e-6},
        {"check": "B2 integer promises identical to stage 7", "expected": True, "actual": b2rep["integer_promises_identical"]},
        {"check": "historical pinball reproduces 1.4827 / 1.3892 / 1.5761 / 1.5613 (4 dp)", "expected": "[1.4827, 1.3892, 1.5761, 1.5613]",
         "actual": str([round(v, 4) for v in hist.pinball_q090_integer_days.iloc[:4]])},
    ])], ignore_index=True)
    checks["pass"] = checks.expected.astype(str) == checks.actual.astype(str)

    for name, df in [*tables.items(), ("partition_manifest", manifest), ("feature_build", builds),
                     ("historical_reproduction", hist), ("checks", checks)]:
        df.to_csv(stage / f"{name}.csv", index=False)
    (stage / "b2_reproduction.json").write_text(json.dumps(b2rep, indent=2))
    (stage / "lineage.json").write_text(json.dumps({
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "stage": "prep (execution step 1; no new E metric)",
        "config_sha256": sha256(CFG_PATH), "registered_sha256": registered_sha(),
        "mart_sha256": sha256(ROOT / "outputs" / "marts" / "orders_mart.csv"), "versions": versions(),
        "checks_pass": bool(checks["pass"].all())}, indent=2))
    gate(checks, "prep")
    return {"tables": tables, "builds": builds, "checks": checks, "b2": b2rep, "hist": hist, "manifest": manifest}


if __name__ == "__main__":
    stage = sys.argv[1] if len(sys.argv) > 1 else "prep"
    if stage == "select":                      # checkpoint 3, step 2 only (owner go-ahead 2026-10-19)
        from .e1_pipeline import run_select
        r = run_select()
        print(json.dumps(r["out"], indent=1, default=str))
        print(r["lin"].to_string(index=False))
        print(r["hgb"].to_string(index=False))
        raise SystemExit(0)
    if stage == "select-repro":                # reproduction run: new directory, original never overwritten
        from .e1_pipeline import run_select
        r = run_select(out_name=sys.argv[2], reproduces="select")
        print(json.dumps(r["out"], indent=1, default=str))
        print(r["comparison"].to_string())
        raise SystemExit(0)
    if stage == "fit-freeze":                  # steps 3-5 (owner go-ahead 2026-10-20)
        from .e1_pipeline import run_fit_freeze
        r = run_fit_freeze()
        print(json.dumps(r["summary"], indent=1, default=str))
        raise SystemExit(0)
    if stage == "score":                       # step 6: E once; require_frozen + C-shift recomputation first
        from .e1_pipeline import run_score
        print(json.dumps(run_score(), indent=1, default=str))
        raise SystemExit(0)
    if stage != "prep":
        raise SystemExit("enabled stages: prep, select, select-repro, fit-freeze, score")
    r = prep()
    print(r["tables"]["segment_counts"].to_string(index=False))
    print(r["manifest"].to_string(index=False))
    print(r["builds"].to_string(index=False))
    print(json.dumps(r["b2"], indent=1))
    print(r["checks"][["check", "pass"]].to_string(index=False))
