"""E1 freeze record. Evaluation-set (E) scoring refuses to run unless a complete, untampered record exists.

Checks in `require_frozen` (every one raises FreezeError; nothing is skipped when a field is empty):
  1. record bytes == the SHA-256 written next to it at freeze time (FREEZE.sha256) and reported to the owner;
  2. schema: every required key present, non-empty, right type, nested fields complete;
  3. config file == record == latest registered hash;
  4. partition id hashes RECOMPUTED from the actual scoring inputs == record (all five segments);
  5. run list == the registered E runs: each is either 'frozen' (model file, feature rule, settings, and a shift
     for every shifted run, with n and k consistent with q) or 'failed' with a reason (-> 'not evaluable');
  6. every model file re-hashed;
  7. shifts optionally RECOMPUTED from the frozen models on C (callback) and compared;
  8. code fingerprint over every .py of the package (the whole feature and prediction path) + library versions;
  9. thresholds == the constants the verdict functions use.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Callable, Iterable

REQUIRED = ["config_sha256", "partition_id_sha256", "feature_rules", "preprocessing_and_selected_hyperparameters",
            "fitted_model_files_sha256", "shifts_by_policy_and_q", "scoring_code_sha256", "thresholds"]
EXTRA_REQUIRED = ["runs", "code_files_sha256", "environment"]   # implementation detail; config lists the minimum
SEGMENTS = ("F0", "V", "F", "C", "E")
CAL_N = 17056

# Registered runs scored on E (config `runs`, `quantiles`, `seller_snapshot`). key = "<run>@<q>".
REGISTERED_RUNS = {
    "B1@0.90":       {"model": "state",  "snapshot": "none", "q": 0.90,   "shifted": False},
    "B1c@0.90":      {"model": "state",  "snapshot": "none", "q": 0.90,   "shifted": True},
    "B2@0.90":       {"model": "linear", "snapshot": "O",    "q": 0.90,   "shifted": True},
    "B3@0.90":       {"model": "linear", "snapshot": "U",    "q": 0.90,   "shifted": True},
    "Cstar@0.90":    {"model": "linear", "snapshot": "U",    "q": 0.90,   "shifted": True},
    "Dstar@0.90":    {"model": "hgb",    "snapshot": "U",    "q": 0.90,   "shifted": True},
    "B1c@0.9126":    {"model": "state",  "snapshot": "none", "q": 0.9126, "shifted": True},
    "Cstar@0.9126":  {"model": "linear", "snapshot": "U",    "q": 0.9126, "shifted": True},
    "Dstar@0.9126":  {"model": "hgb",    "snapshot": "U",    "q": 0.9126, "shifted": True},
}

# Pre-registered thresholds (config `metrics`, `hypotheses`, `bootstrap`); the verdict functions use these values.
THRESHOLDS = {
    "practical_rule": {"days": 1.0, "coverage_pts": 1.0},
    "monthly_reliability": {"min_orders": 1000, "max_pts_below_target": 3.0},
    "H1": {"days": 0.5, "coverage_pts": 0.5},
    "H2": {"relative_improvement": 0.02, "interval": "percentile 95%, upper end < 0"},
    "ties": {"tie_rel": 0.001, "adopt_rel": 0.01},
    "bootstrap": {"replicates": 2000, "seed": 20261015, "unit": "purchase week"},
}

_HEX = re.compile(r"^[0-9a-f]{64}$")


class FreezeError(RuntimeError):
    pass


def file_sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def id_sha256(order_ids: Iterable) -> str:
    """Same definition as e1_data.id_sha256: SHA-256 of the sorted ids, one per line."""
    return hashlib.sha256("\n".join(sorted(map(str, order_ids))).encode()).hexdigest()


# ------------------------------------------------------------------ code fingerprint
def package_files(pkg_dir: Path) -> list[Path]:
    return sorted(Path(pkg_dir).glob("*.py"))


def code_fingerprint(pkg_dir: Path) -> tuple[str, dict]:
    """(combined SHA-256, {file name: SHA-256}) over every module of the package, so a change anywhere on the
    feature / prediction path (features.py, date_policy.py, e1_*.py, io.py, ...) is caught."""
    files = {f.name: file_sha(f) for f in package_files(pkg_dir)}
    if not files:
        raise FreezeError(f"no python files under {pkg_dir}")
    combined = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return combined, files


def environment() -> dict:
    import numpy, pandas, scipy, sklearn
    return {"numpy": numpy.__version__, "pandas": pandas.__version__, "scipy": scipy.__version__,
            "scikit-learn": sklearn.__version__}


def scoring_code_sha(files: list[Path]) -> str:            # kept for the existing caller; prefer code_fingerprint
    return hashlib.sha256(b"".join(Path(f).read_bytes() for f in files)).hexdigest()


# ------------------------------------------------------------------ schema
def _hex(v, what):
    if not isinstance(v, str) or not _HEX.match(v):
        raise FreezeError(f"{what}: not a SHA-256 hex string")


def _nonempty_dict(rec, key):
    v = rec.get(key)
    if not isinstance(v, dict) or not v:
        raise FreezeError(f"freeze record: '{key}' must be a non-empty object")
    return v


def validate_record(rec: dict) -> None:
    """Structure only (no files): raises on any missing, empty, mistyped or incomplete field."""
    if not isinstance(rec, dict):
        raise FreezeError("freeze record is not an object")
    missing = [k for k in REQUIRED + EXTRA_REQUIRED if k not in rec or rec[k] in (None, {}, [], "")]
    if missing:
        raise FreezeError(f"freeze record incomplete or empty: {missing}")
    _hex(rec["config_sha256"], "config_sha256")
    _hex(rec["scoring_code_sha256"], "scoring_code_sha256")

    parts = _nonempty_dict(rec, "partition_id_sha256")
    if set(parts) != set(SEGMENTS):
        raise FreezeError(f"partition_id_sha256 must list exactly {SEGMENTS}, got {sorted(parts)}")
    for s, h in parts.items():
        _hex(h, f"partition_id_sha256[{s}]")

    runs = _nonempty_dict(rec, "runs")
    if set(runs) != set(REGISTERED_RUNS):
        raise FreezeError(f"runs must be exactly the registered E runs; missing {sorted(set(REGISTERED_RUNS) - set(runs))}, "
                          f"unregistered {sorted(set(runs) - set(REGISTERED_RUNS))}")
    feats = _nonempty_dict(rec, "feature_rules")
    prep = _nonempty_dict(rec, "preprocessing_and_selected_hyperparameters")
    models = _nonempty_dict(rec, "fitted_model_files_sha256")
    shifts = _nonempty_dict(rec, "shifts_by_policy_and_q")
    for key, reg in REGISTERED_RUNS.items():
        st = runs[key]
        status = st.get("status") if isinstance(st, dict) else None
        if status == "failed":
            if not str(st.get("reason", "")).strip():
                raise FreezeError(f"run {key}: 'failed' needs a reason")
            continue
        if status != "frozen":
            raise FreezeError(f"run {key}: status must be 'frozen' or 'failed', got {status!r}")
        fr = feats.get(key)
        if not isinstance(fr, dict) or fr.get("snapshot") != reg["snapshot"]:
            raise FreezeError(f"run {key}: feature rule must state snapshot = {reg['snapshot']!r}")
        if reg["model"] != "state" and not fr.get("features"):
            raise FreezeError(f"run {key}: feature list missing")
        pp = prep.get(key)
        if not isinstance(pp, dict) or not pp or pp.get("model") != reg["model"] or pp.get("q") != reg["q"]:
            raise FreezeError(f"run {key}: preprocessing/hyperparameters missing or model/q mismatch")
        mf = models.get(key)
        if not isinstance(mf, dict) or not mf.get("path"):
            raise FreezeError(f"run {key}: model file missing")
        _hex(mf.get("sha256"), f"run {key} model sha256")
        if reg["shifted"]:
            sh = shifts.get(key)
            if not isinstance(sh, dict):
                raise FreezeError(f"run {key}: shift missing")
            n, k, s = sh.get("n"), sh.get("k"), sh.get("shift_days")
            if n != CAL_N:
                raise FreezeError(f"run {key}: calibration n = {n}, expected {CAL_N}")
            if k != math.ceil((n + 1) * reg["q"]):
                raise FreezeError(f"run {key}: k = {k} is not ceil((n+1)q) for q = {reg['q']}")
            if not isinstance(s, (int, float)) or isinstance(s, bool) or not math.isfinite(s):
                raise FreezeError(f"run {key}: shift_days must be a finite number")
        elif key in shifts:
            raise FreezeError(f"run {key} is registered without a shift but the record has one")
    if rec["thresholds"] != THRESHOLDS:
        raise FreezeError("thresholds differ from the pre-registered values")
    files = _nonempty_dict(rec, "code_files_sha256")
    for name, h in files.items():
        _hex(h, f"code_files_sha256[{name}]")


# ------------------------------------------------------------------ write / verify
def write_freeze(path: Path, record: dict) -> str:
    """Validate, write once, and write the record's own SHA-256 to FREEZE.sha256. Returns that hash."""
    validate_record(record)
    path = Path(path)
    if path.exists():
        raise FreezeError(f"{path} already exists: a freeze is written once")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True))
    sha = file_sha(path)
    (path.parent / "FREEZE.sha256").write_text(f"{sha}  {path.name}\n")
    return sha


def require_frozen(path: Path, root: Path, config_path: Path, *, registered_config_sha: str,
                   partition_ids: dict, pkg_dir: Path,
                   recompute_shift: Callable[[str], float] | None = None, tol: float = 1e-9) -> dict:
    """Verify the record against the files and inputs actually used for E scoring; raise FreezeError on any gap."""
    path = Path(path)
    if not path.exists():
        raise FreezeError("no freeze record: E may not be scored before the freeze (execution step 5)")
    sha_file = path.parent / "FREEZE.sha256"
    if not sha_file.exists():
        raise FreezeError("FREEZE.sha256 missing: the record cannot be checked")
    if file_sha(path) != sha_file.read_text().split()[0]:
        raise FreezeError("freeze record changed after it was written (hash mismatch)")
    rec = json.loads(path.read_text())
    validate_record(rec)

    actual_cfg = file_sha(config_path)
    if not (rec["config_sha256"] == actual_cfg == registered_config_sha):
        raise FreezeError("config differs between the record, the file and the latest registration")

    if set(partition_ids) != set(SEGMENTS):
        raise FreezeError(f"scoring inputs must provide ids for {SEGMENTS}")
    for s in SEGMENTS:
        if id_sha256(partition_ids[s]) != rec["partition_id_sha256"][s]:
            raise FreezeError(f"partition {s}: ids used now differ from the frozen sample list")

    for key, st in rec["runs"].items():
        if st["status"] != "frozen":
            continue
        mf = rec["fitted_model_files_sha256"][key]
        f = Path(root) / mf["path"]
        if not f.exists() or file_sha(f) != mf["sha256"]:
            raise FreezeError(f"run {key}: model file missing or changed after the freeze")
        if recompute_shift is not None and REGISTERED_RUNS[key]["shifted"]:
            s_now = recompute_shift(key)
            if not math.isfinite(s_now) or abs(s_now - rec["shifts_by_policy_and_q"][key]["shift_days"]) > tol:
                raise FreezeError(f"run {key}: shift recomputed on C ({s_now}) differs from the record")

    combined, files = code_fingerprint(pkg_dir)
    if rec["scoring_code_sha256"] != combined or rec["code_files_sha256"] != files:
        changed = sorted(n for n in set(files) | set(rec["code_files_sha256"])
                         if files.get(n) != rec["code_files_sha256"].get(n))
        raise FreezeError(f"package code changed after the freeze: {changed}")
    if rec["environment"] != environment():
        raise FreezeError("library versions differ from the freeze")
    return rec


# ------------------------------------------------------------------ input CONTENT identity (post-hoc hardening, 2026-10-20)
def canonical_frame_sha(df) -> str:
    """SHA-256 of a frame's CONTENT, independent of row / column order and of CSV formatting on disk:
    rows sorted by order_id (or the index), columns sorted by name, floats as repr-exact %.17g, datetimes as ISO
    with microseconds, missing values as empty strings, written as UTF-8 CSV with a header."""
    import pandas as pd
    d = df.copy()
    if "order_id" not in d.columns:
        d = d.reset_index()
    d = d[sorted(d.columns, key=str)]
    for c in d.columns:
        if pd.api.types.is_datetime64_any_dtype(d[c]):
            d[c] = d[c].dt.strftime("%Y-%m-%dT%H:%M:%S.%f")
    d = d.sort_values([c for c in ["order_id"] if c in d.columns] or list(d.columns[:1]), kind="mergesort")
    text = d.to_csv(index=False, float_format="%.17g", na_rep="", lineterminator="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


INPUT_KEYS = ("rows_F0", "rows_V", "rows_F", "rows_C", "rows_E", "seller_history", "stage7_reference")


def require_inputs(expected: dict, actual: dict) -> None:
    """Every input content hash must match: same order ids with changed labels, features or reference dates are refused."""
    if not isinstance(expected, dict) or set(expected) != set(INPUT_KEYS):
        raise FreezeError(f"input identity record must list exactly {INPUT_KEYS}")
    for k in INPUT_KEYS:
        _hex(expected[k], f"input identity {k}")
        if actual.get(k) != expected[k]:
            raise FreezeError(f"input content changed since the freeze: {k}")


def not_evaluable_runs(rec: dict) -> list[str]:
    """Runs recorded as failed: reported as 'not evaluable', never as 'not supported', never substituted."""
    return sorted(k for k, v in rec["runs"].items() if v["status"] == "failed")
