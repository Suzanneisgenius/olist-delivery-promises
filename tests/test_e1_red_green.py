"""Behaviour tests for the four review defects, written so they run against BOTH the pre-fix code
(checkpoint-2 bundle) and the fixed code. Only behaviour is asserted (accepted vs refused), never a new API,
so a failure on the old code means the defect is real, and a pass on the new code means it is fixed.

    red:   PYTHONPATH=<copy with the old e1_freeze.py / e1_models.py>/src pytest tests/test_e1_red_green.py
    green: PYTHONPATH=src pytest tests/test_e1_red_green.py
"""
import copy
import inspect
import json

import numpy as np
import pytest

from olist_analytics import e1_freeze as Z
from olist_analytics import e1_models as M

NEW_API = "partition_ids" in inspect.signature(Z.require_frozen).parameters
SEGS = ("F0", "V", "F", "C", "E")
IDS = {s: [f"{s}-{i}" for i in range(5)] for s in SEGS}


# ------------------------------------------------------------------ a valid record for whichever version is installed
def _setup(tmp_path):
    cfgf = tmp_path / "cfg.yaml"; cfgf.write_text("a: 1\n")
    pkg = tmp_path / "pkg"; pkg.mkdir()
    (pkg / "e1_models.py").write_text("y = 2\n")
    (tmp_path / "models").mkdir()
    if NEW_API:
        rec = {k: {} for k in Z.REQUIRED + Z.EXTRA_REQUIRED}
        for key, reg in Z.REGISTERED_RUNS.items():
            f = tmp_path / "models" / f"{key}.bin"; f.write_bytes(key.encode())
            rec["runs"][key] = {"status": "frozen"}
            rec["feature_rules"][key] = {"snapshot": reg["snapshot"],
                                         "features": [] if reg["model"] == "state" else ["distance_km"]}
            rec["preprocessing_and_selected_hyperparameters"][key] = {"model": reg["model"], "q": reg["q"]}
            rec["fitted_model_files_sha256"][key] = {"path": f"models/{key}.bin", "sha256": Z.file_sha(f)}
            if reg["shifted"]:
                rec["shifts_by_policy_and_q"][key] = {"n": Z.CAL_N, "k": int(np.ceil((Z.CAL_N + 1) * reg["q"])),
                                                      "shift_days": 6.0}
        combined, files = Z.code_fingerprint(pkg)
        rec.update(config_sha256=Z.file_sha(cfgf), partition_id_sha256={s: Z.id_sha256(v) for s, v in IDS.items()},
                   scoring_code_sha256=combined, code_files_sha256=files, thresholds=copy.deepcopy(Z.THRESHOLDS),
                   environment=Z.environment())
    else:                                                   # checkpoint-2 format
        f = tmp_path / "models" / "Cstar.bin"; f.write_bytes(b"model")
        rec = {"config_sha256": Z.file_sha(cfgf),
               "partition_id_sha256": {s: "%064x" % i for i, s in enumerate(SEGS, 1)},
               "feature_rules": {"Cstar@0.90": {"snapshot": "U"}},
               "preprocessing_and_selected_hyperparameters": {"Cstar@0.90": {"model": "linear", "q": 0.90}},
               "fitted_model_files_sha256": {"models/Cstar.bin": Z.file_sha(f)},
               "shifts_by_policy_and_q": {"Cstar@0.90": {"n": 17056, "k": 15351, "shift_days": 6.0}},
               "scoring_code_sha256": Z.scoring_code_sha([pkg / "e1_models.py"]),
               "thresholds": {"H2": {"relative_improvement": 0.02}}}
    path = tmp_path / "freeze" / "FREEZE.json"
    Z.write_freeze(path, rec)
    return path, cfgf, pkg


def _verify(tmp_path, path, cfgf, pkg):
    if NEW_API:
        return Z.require_frozen(path, tmp_path, cfgf, registered_config_sha=Z.file_sha(cfgf), partition_ids=IDS,
                                pkg_dir=pkg, recompute_shift=lambda key: 6.0)
    return Z.require_frozen(path, tmp_path, cfgf, [pkg / "e1_models.py"])


def _edit(path, fn):
    rec = json.loads(path.read_text())
    fn(rec)
    path.write_text(json.dumps(rec, indent=2, sort_keys=True))


def _first_shift(rec):
    return next(iter(rec["shifts_by_policy_and_q"].values()))


TAMPER = {
    "sample list (partition id hash) changed": lambda r: r["partition_id_sha256"].update(E="0" * 64),
    "calibration shift changed to 1000 days": lambda r: _first_shift(r).update(shift_days=1000.0),
    "threshold changed (H2 2% -> 1%)": lambda r: r["thresholds"]["H2"].update(relative_improvement=0.01),
    "thresholds emptied": lambda r: r.update(thresholds={}),
    "model file list emptied": lambda r: r.update(fitted_model_files_sha256={}),
}


def test_untampered_record_is_accepted(tmp_path):
    path, cfgf, pkg = _setup(tmp_path)
    assert _verify(tmp_path, path, cfgf, pkg)


@pytest.mark.parametrize("case", list(TAMPER))
def test_edited_freeze_record_blocks_e_scoring(tmp_path, case):
    path, cfgf, pkg = _setup(tmp_path)
    _edit(path, TAMPER[case])
    with pytest.raises(Z.FreezeError):
        _verify(tmp_path, path, cfgf, pkg)


# ------------------------------------------------------------------ invalid labels / predictions must raise
BAD_VALUES = {"NaN": np.nan, "+inf": np.inf, "-inf": -np.inf}


@pytest.mark.parametrize("bad", list(BAD_VALUES))
@pytest.mark.parametrize("where", ["label", "prediction"])
@pytest.mark.parametrize("fn", ["shift", "pinball", "policy_score"])
def test_non_finite_values_raise(fn, where, bad):
    y, p = np.arange(1.0, 101.0), np.full(100, 5.0)
    (y if where == "label" else p)[3] = BAD_VALUES[bad]      # index 3: never the k-th residual at q = 0.90
    call = {"shift": lambda: M.shift(y, p, 0.90), "pinball": lambda: M.pinball(y, p, 0.90),
            "policy_score": lambda: M.policy_score(y, p)}[fn]
    with pytest.raises(ValueError):
        call()


@pytest.mark.parametrize("n_pred", [1, 99, 101])           # 1 = would broadcast silently in numpy
@pytest.mark.parametrize("fn", ["shift", "pinball", "policy_score"])
def test_unequal_lengths_raise(fn, n_pred):
    y, p = np.arange(1.0, 101.0), np.full(n_pred, 5.0)
    call = {"shift": lambda: M.shift(y, p, 0.90), "pinball": lambda: M.pinball(y, p, 0.90),
            "policy_score": lambda: M.policy_score(y, p)}[fn]
    with pytest.raises(ValueError):
        call()
