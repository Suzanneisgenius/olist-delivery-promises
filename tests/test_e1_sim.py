"""Supplementary calibration simulation (synthetic only)."""
import importlib.util
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("sim", Path(__file__).parents[1] / "scripts" / "e1_calibration_sim.py")
sim = importlib.util.module_from_spec(spec); spec.loader.exec_module(sim)
SMALL = dict(sim.PARAMS, reps=20, n_cal=500, n_eval=1000)


def test_label_usable_only_if_delivered_before_freeze():
    rng = np.random.default_rng(0)
    y = np.array([1.0, 50.0, 200.0])
    keep = sim.observed_by_freeze(y, rng, 90)
    assert not keep[2]                                    # 200 days can never arrive inside a 90-day window


def test_reproducible_and_same_promise_under_time_shift():
    r1, s1 = sim.run(SMALL)
    r2, s2 = sim.run(SMALL)
    assert r1.equals(r2)
    s = s1.set_index("scenario")
    # S3 keeps the S1 shift (same calibration data); only the outcome distribution moves
    assert np.isclose(s.loc[sim.SCENARIOS[0], "shift_mean"], s.loc[sim.SCENARIOS[2], "shift_mean"])
    assert s.loc[sim.SCENARIOS[1], "cal_n_mean"] < SMALL["n_cal"]
    assert s.loc[sim.SCENARIOS[2], "coverage_mean"] < s.loc[sim.SCENARIOS[0], "coverage_mean"] < s.loc[sim.SCENARIOS[3], "coverage_mean"]


def test_paired_run_shares_evaluation_and_isolates_selection():
    spec2 = importlib.util.spec_from_file_location("simp", Path(__file__).parents[1] / "scripts" / "e1_calibration_sim_paired.py")
    simp = importlib.util.module_from_spec(spec2); spec2.loader.exec_module(simp)
    reps, summ, diffs = simp.run(dict(simp.PARAMS, reps=30, n_cal=800, n_eval=2000))
    w = reps.pivot(index="rep", columns="scenario", values="mean_promised_days")
    assert np.allclose(w[simp.SCEN[0]], w[simp.SCEN[3]]) and np.allclose(w[simp.SCEN[0]], w[simp.SCEN[4]])
    n = reps.pivot(index="rep", columns="scenario", values="cal_n_used")
    assert (n[simp.SCEN[1]] == n[simp.SCEN[2]]).all()                  # size control has the same n as S2
    assert (reps.n_eval == 2000).all()
