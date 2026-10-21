"""E1 checkpoint-2 tests: future labels, training-only preprocessing, partitions, rounding, calibration with q,
per-order/summary reconciliation, HGB settings, week bootstrap, registration gate. Synthetic data only (fast)."""
import copy
import json

import numpy as np
import pandas as pd
import pytest

import olist_analytics.e1_data as D
import olist_analytics.e1_models as M
import olist_analytics.run_e1 as R
from olist_analytics.features import LeakageError, seller_snapshot
from olist_analytics.gate import ReleaseBlocked

CFG = D.cfg()
SPEC = CFG["models"]["linear_registered"]


def frame(n, rng, start="2017-01-05"):
    P = pd.Timestamp(start) + pd.to_timedelta(rng.integers(0, 120, n), unit="D")
    return pd.DataFrame({
        "order_id": [f"o{i}" for i in range(n)], "order_purchase_timestamp": P,
        "order_delivered_customer_date": P + pd.to_timedelta(rng.integers(2, 30, n), unit="D"),
        "distance_km": rng.uniform(1, 3000, n), "same_state": rng.integers(0, 2, n).astype(float),
        "weight_g_sum": rng.uniform(100, 5000, n), "items_price_sum": rng.uniform(10, 500, n),
        "items_freight_sum": rng.uniform(5, 60, n), "freight_ratio": rng.uniform(0.05, 0.5, n),
        "n_item_lines": rng.integers(1, 4, n), "purchase_dow": P.weekday,
        "seller_hist_late_rate": rng.uniform(0, 0.2, n), "seller_hist_handling_median_h": rng.uniform(10, 100, n),
        "seller_hist_n_delivered": rng.integers(0, 200, n).astype(float),
        "customer_state_reported": rng.choice(["SP", "RJ", "MG"], n), "seller_state": rng.choice(["SP", "PR"], n)})


# ------------------------------------------------------------------ future labels
def test_used_rows_need_a_label_known_at_the_cutoff():
    pop = pd.DataFrame({"order_id": ["a", "b", "c"],
                        "order_purchase_timestamp": pd.to_datetime(["2017-08-01", "2017-09-20", "2017-09-25"]),
                        "order_delivered_customer_date": pd.to_datetime(["2017-08-10", "2017-11-30", "2017-12-01"]),
                        "is_late": [0, 0, 1]})
    segs = D.segment_rows(pop, CFG)
    assert segs["V"]["eligible"].order_id.tolist() == ["a", "b", "c"]
    assert segs["V"]["used"].order_id.tolist() == ["a", "b"]          # delivered ON the cutoff is not known before it


def test_seller_snapshot_ignores_labels_delivered_at_or_after_T():
    h = pd.DataFrame({"single_seller_id": ["s", "s", "s"], "outcome_bucket": ["A", "L", "A"],
                      "order_purchase_timestamp": pd.to_datetime(["2017-01-01", "2017-01-20", "2017-02-20"]),
                      "order_delivered_customer_date": pd.to_datetime(["2017-01-10", "2017-03-01", "2017-02-25"]),
                      "is_late": [0, 1, 0], "handling_hours": [10.0, 20.0, 30.0], "is_stage_eligible": [True, True, True]})
    snap, meta = seller_snapshot(h, pd.Timestamp("2017-03-01"), k=10)
    assert snap.loc["s", "seller_hist_n_delivered"] == 2               # the order delivered ON 03-01 is excluded
    assert snap.loc["s", "seller_hist_n_placed"] == 3                  # placing an order is known at purchase
    assert pd.Timestamp(meta["max_label_delivery"]) < pd.Timestamp("2017-03-01")


def test_snapshot_rules():
    rows = pd.DataFrame({"order_purchase_timestamp": pd.to_datetime(["2018-04-15 10:00", "2018-06-30 23:00"])})
    assert D.snapshot_times(rows, "E", "U").dt.strftime("%Y-%m-%d").tolist() == ["2018-04-01", "2018-06-01"]
    assert D.snapshot_times(rows, "E", "O").dt.strftime("%Y-%m-%d").tolist() == ["2018-04-01", "2018-04-01"]
    with pytest.raises(ValueError):
        D.snapshot_times(rows, "F0", "O")


# ------------------------------------------------------------------ partitions
def test_partition_checks_catch_overlap_and_duplicates():
    def seg(ids, cut="2017-01-02"):
        return {"eligible": pd.DataFrame({"order_id": ids}),
                "used": pd.DataFrame({"order_id": ids, "order_delivered_customer_date": pd.Timestamp("2017-01-01")})}
    segs = {"F0": seg(["a"]), "V": seg(["b"]), "F": seg(["a", "b"]), "C": seg(["c", "c"]), "E": seg(["b"])}
    chk = D.partition_checks(segs, CFG).set_index("check")
    assert not chk.loc["F and E share no order", "pass"] and not chk.loc["C: no duplicate order ids", "pass"]
    assert chk.loc["F0 and V share no order", "pass"]


# ------------------------------------------------------------------ preprocessing fitted on training rows only
def test_linear_preprocessing_is_learned_from_training_rows_only():
    rng = np.random.default_rng(0)
    tr, ev = frame(400, rng), frame(100, rng)
    ev["customer_state_reported"] = "AC"                               # unseen state
    ev["distance_km"] *= 50                                            # very different scale
    y = rng.integers(2, 30, 400)
    m = M.LinearModel(SPEC, 0.9, target="log1p").fit(tr, y)
    sc = m.pipe.named_steps["pre"].named_transformers_["log"].named_steps["sc"]
    assert np.isclose(sc.mean_[0], np.log1p(tr.distance_km).mean())    # first logged column = distance_km
    before = m.predict(tr)
    m.predict(ev)                                                      # scoring eval rows must not refit anything
    assert np.allclose(before, m.predict(tr))
    enc = m.pipe.named_steps["pre"].named_transformers_["cat"]
    assert "AC" not in set(enc.categories_[0])


def test_hgb_settings_and_training_only_categories():
    rng = np.random.default_rng(1)
    tr, ev = frame(300, rng), frame(50, rng)
    ev["seller_state"] = "XX"
    h = M.HGBModel(SPEC, CFG["models"]["hgb"], 0.9, max_depth=2, max_iter=20).fit(tr, rng.integers(2, 30, 300))
    assert h.model.early_stopping is False and h.model.loss == "quantile" and h.model.quantile == 0.9
    assert h.model.max_depth == 2 and h.model.max_iter == 20 and h.model.random_state == 20261015
    assert "XX" not in set(h.enc.categories_[1])
    assert np.isfinite(h.predict(ev)).all()


def test_dow_categorical_and_raw_target_variants_fit():
    rng = np.random.default_rng(2)
    tr = frame(300, rng)
    y = rng.integers(2, 30, 300)
    for kw in ({"dow_categorical": True}, {"target": "days"}, {"target": "days", "alpha": 0.01}):
        p = M.LinearModel(SPEC, 0.9, **kw).fit(tr, y).predict(tr)
        assert np.isfinite(p).all()
    cat = M.LinearModel(SPEC, 0.9, dow_categorical=True).pipe.named_steps["pre"].transformers
    assert "purchase_dow" in cat[2][2] and "purchase_dow" not in cat[0][2] + cat[1][2]


# ------------------------------------------------------------------ rounding and calibration with q
def test_promise_is_max_one_ceil_of_unrounded_prediction_plus_shift():
    assert M.promise(np.array([0.2, 3.0, 3.0001, 7.5]), 0.0).tolist() == [1, 3, 4, 8]
    assert M.promise(np.array([2.4, 9.0]), 1.7).tolist() == [5, 11]


@pytest.mark.parametrize("q", [0.90, 0.9126])
def test_shift_uses_the_order_statistic_for_its_own_q(q):
    y, pred = np.arange(1.0, 18.0), np.zeros(17)                       # scores 1..17, n = 17
    k = int(np.ceil(18 * q))                                           # 17 for both here
    assert M.shift(y, pred, q) == float(k)
    y, pred = np.arange(1.0, 101.0), np.zeros(100)
    assert M.shift(y, pred, q) == float(np.ceil(101 * q))              # 91 for 0.90, 93 for 0.9126


def test_calibration_sort_index_uses_sorted_residuals():
    y = np.array([9.0, 1.0, 5.0, 3.0, 7.0, 2.0, 8.0, 4.0, 6.0])         # residuals unsorted, n = 9
    assert M.shift(y, np.zeros(9), 0.5) == 5.0                          # k = ceil(10 * 0.5) = 5 -> 5th smallest


def test_calibration_with_repeated_residuals():
    y = np.array([3.0, 3.0, 3.0, 3.0, 8.0, 8.0, 8.0, 8.0, 8.0])
    assert M.shift(y, np.zeros(9), 0.4) == 3.0                          # k = 4 -> still inside the tie at 3
    assert M.shift(y, np.zeros(9), 0.5) == 8.0                          # k = 5 -> first 8


def test_calibration_allows_a_negative_shift():
    y = np.arange(1.0, 11.0)
    pred = y + 3.0                                                      # model overshoots by 3 days everywhere
    s = M.shift(y, pred, 0.9)
    assert s == -3.0                                                    # no silent clip at 0
    assert M.promise(pred, s).tolist() == [int(v) for v in y]


def test_too_small_calibration_set_raises_instead_of_using_zero():
    with pytest.raises(M.PredictionError):
        M.shift(np.arange(9.0), np.zeros(9), 0.9126)                    # k = ceil(10 * 0.9126) = 10 > 9


def test_each_q_gets_its_own_shift():
    rng = np.random.default_rng(6)
    y, pred = rng.integers(1, 40, 1000).astype(float), np.full(1000, 10.0)
    s90, s91 = M.shift(y, pred, 0.90), M.shift(y, pred, 0.9126)
    assert s90 == np.sort(y - pred)[int(np.ceil(1001 * 0.90)) - 1]
    assert s91 == np.sort(y - pred)[int(np.ceil(1001 * 0.9126)) - 1] and s91 >= s90


def test_integer_boundary_is_not_pushed_up_by_float_noise():
    assert M.promise(np.array([2.7]), 0.3).tolist() == [3]              # 2.7 + 0.3 = 3.0000000000000004
    assert M.promise(np.array([3.0 + 1e-6]), 0.0).tolist() == [4]       # a real excess still rounds up
    assert M.promise(np.array([-2.0]), 0.0).tolist() == [1]             # floor of one day


def test_non_finite_or_missing_predictions_are_errors_not_drops():
    with pytest.raises(M.PredictionError):
        M.promise(np.array([3.0, np.nan]))
    with pytest.raises(M.PredictionError):
        M.checked(np.array([1.0, 2.0]), 3)                              # a model returning fewer rows


def test_log_model_residuals_are_on_the_day_scale():
    rng = np.random.default_rng(7)
    tr = frame(300, rng)
    y = rng.integers(2, 30, 300)
    m = M.LinearModel(SPEC, 0.9, target="log1p").fit(tr, y)
    pred = m.predict(tr)                                                # back-transformed days
    assert np.allclose(pred, np.expm1(m.pipe.predict(tr[m.cols])))
    assert np.isclose(M.shift(y, pred, 0.9), np.sort(y - pred)[int(np.ceil(301 * 0.9)) - 1])


def test_shift_is_computed_on_unrounded_predictions():
    y = np.array([5, 6, 7, 8, 9, 10, 11, 12, 13, 14], float)
    raw = y - 0.4                                                      # residual 0.4 for every order
    assert np.isclose(M.shift(y, raw, 0.5), 0.4)                       # rounding first would give 0 or -1


# ------------------------------------------------------------------ per-order vs summary
def test_per_order_values_reconcile_with_summaries():
    rng = np.random.default_rng(3)
    y, d = rng.integers(1, 40, 500), rng.integers(1, 40, 500)
    assert np.isclose(M.pinball_per_order(y, d, 0.9).mean(), M.pinball(y, d, 0.9))
    s = M.policy_score(y, d)
    assert s["n_missed"] == int((y > d).sum()) and np.isclose(s["coverage"], 1 - s["n_missed"] / 500)
    assert np.isclose(s["mean_overrun_days_when_missed"], (y - d)[y > d].mean())


def test_pinball_known_values():
    assert np.isclose(M.pinball([10], [8], 0.9), 1.8) and np.isclose(M.pinball([8], [10], 0.9), 0.2)


# ------------------------------------------------------------------ week bootstrap
def test_bootstrap_pools_orders_and_shares_draws_across_models():
    weeks = np.array([0] * 9 + [1])                                    # unequal week sizes
    a = np.array([1.0] * 9 + [10.0])
    b = a * 2
    full = np.array([[0, 1]])                                          # one replicate = every week once
    r = M.bootstrap_pooled({"a": a, "b": b}, weeks, full)
    assert np.isclose(r["a"][0], a.mean())                             # 1.9 (per order), not 5.5 (per week)
    rng = np.random.default_rng(4)
    draws = M.week_draws(2, 50, rng)
    r = M.bootstrap_pooled({"a": a, "b": b}, weeks, draws)
    assert np.allclose(r["b"], 2 * r["a"])                             # same weeks for both series (paired)


def test_moving_block_draws_have_valid_starts_and_length():
    d = M.week_draws(17, 500, np.random.default_rng(5), scheme="moving", block=2)
    assert d.shape == (500, 17) and d.min() >= 0 and d.max() <= 16
    assert ((d[:, 1::2][:, :8] - d[:, 0::2][:, :8]) == 1).all()        # each block = 2 consecutive weeks


# ------------------------------------------------------------------ registration gate
def test_changed_config_blocks_prep(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "OUT", tmp_path)
    monkeypatch.setattr(R, "registered_sha", lambda: "0" * 64)
    with pytest.raises(ReleaseBlocked):
        R.prep()
    assert (tmp_path / "prep" / "qa" / "RELEASE_BLOCKED.json").exists()


# ------------------------------------------------------------------ freeze guard
from olist_analytics import e1_freeze as Z  # noqa: E402

IDS = {s: [f"{s}-{i}" for i in range(5)] for s in Z.SEGMENTS}


def freeze_fixture(tmp_path):
    """A complete synthetic record: config file, a model file per frozen run, a tiny package directory."""
    cfgf = tmp_path / "cfg.yaml"; cfgf.write_text("a: 1\n")
    pkg = tmp_path / "pkg"; pkg.mkdir(exist_ok=True)
    (pkg / "features.py").write_text("x = 1\n"); (pkg / "e1_models.py").write_text("y = 2\n")
    (tmp_path / "models").mkdir(exist_ok=True)
    rec = {k: {} for k in Z.REQUIRED + Z.EXTRA_REQUIRED}
    for key, reg in Z.REGISTERED_RUNS.items():
        f = tmp_path / "models" / f"{key}.bin"; f.write_bytes(key.encode())
        rec["runs"][key] = {"status": "frozen"}
        rec["feature_rules"][key] = {"snapshot": reg["snapshot"], "features": [] if reg["model"] == "state" else ["distance_km"]}
        rec["preprocessing_and_selected_hyperparameters"][key] = {"model": reg["model"], "q": reg["q"]}
        rec["fitted_model_files_sha256"][key] = {"path": f"models/{key}.bin", "sha256": Z.file_sha(f)}
        if reg["shifted"]:
            rec["shifts_by_policy_and_q"][key] = {"n": Z.CAL_N, "k": int(np.ceil((Z.CAL_N + 1) * reg["q"])), "shift_days": 6.0}
    combined, files = Z.code_fingerprint(pkg)
    rec.update(config_sha256=Z.file_sha(cfgf), partition_id_sha256={s: Z.id_sha256(v) for s, v in IDS.items()},
               scoring_code_sha256=combined, code_files_sha256=files, thresholds=copy.deepcopy(Z.THRESHOLDS),
               environment=Z.environment())
    return rec, cfgf, pkg


def verify(tmp_path, rec_path, cfgf, pkg, ids=IDS, **kw):
    return Z.require_frozen(rec_path, tmp_path, cfgf, registered_config_sha=Z.file_sha(cfgf), partition_ids=ids,
                            pkg_dir=pkg, **kw)


def test_e_scoring_refuses_without_a_complete_untampered_freeze(tmp_path):
    rec, cfgf, pkg = freeze_fixture(tmp_path)
    rec_path = tmp_path / "freeze" / "FREEZE.json"
    with pytest.raises(Z.FreezeError):
        verify(tmp_path, rec_path, cfgf, pkg)                                # no record yet
    with pytest.raises(Z.FreezeError):
        Z.write_freeze(rec_path, {"config_sha256": "x"})                     # incomplete record
    Z.write_freeze(rec_path, rec)
    assert verify(tmp_path, rec_path, cfgf, pkg)["config_sha256"] == Z.file_sha(cfgf)
    with pytest.raises(Z.FreezeError):
        Z.write_freeze(rec_path, rec)                                        # written once
    (tmp_path / "models" / "Cstar@0.90.bin").write_bytes(b"retrained")
    with pytest.raises(Z.FreezeError, match="model file"):
        verify(tmp_path, rec_path, cfgf, pkg)                                # model changed after the freeze


def _tamper(rec, path_keys, value):
    d = rec
    for k in path_keys[:-1]:
        d = d[k]
    d[path_keys[-1]] = value


@pytest.mark.parametrize("path_keys,value", [
    (["partition_id_sha256", "E"], "0" * 64),                                # another partition hash
    (["shifts_by_policy_and_q", "Cstar@0.90", "shift_days"], 1000.0),        # 1000-day shift
    (["feature_rules"], {}),                                                 # empty feature rules
    (["thresholds"], {}),                                                    # empty thresholds
    (["fitted_model_files_sha256"], {}),                                     # empty model list (loop would skip)
])
def test_edited_freeze_record_is_refused(tmp_path, path_keys, value):
    """The reviewer's negative cases: each edit made AFTER writing the record must stop E scoring."""
    rec, cfgf, pkg = freeze_fixture(tmp_path)
    rec_path = tmp_path / "freeze" / "FREEZE.json"
    Z.write_freeze(rec_path, rec)
    edited = json.loads(rec_path.read_text())
    _tamper(edited, path_keys, value)
    rec_path.write_text(json.dumps(edited, indent=2, sort_keys=True))
    with pytest.raises(Z.FreezeError, match="hash mismatch"):
        verify(tmp_path, rec_path, cfgf, pkg)
    # even if the hash file is rewritten too, the content checks still refuse it
    (rec_path.parent / "FREEZE.sha256").write_text(Z.file_sha(rec_path) + "  FREEZE.json\n")
    with pytest.raises(Z.FreezeError):
        verify(tmp_path, rec_path, cfgf, pkg, recompute_shift=lambda key: 6.0)


@pytest.mark.parametrize("path_keys,value", [
    # (a well-formed but different partition hash or shift is caught at verification, see the test above)
    (["feature_rules"], {}), (["thresholds"], {}), (["fitted_model_files_sha256"], {}),
    (["partition_id_sha256"], {"E": "0" * 64}), (["shifts_by_policy_and_q", "Cstar@0.90", "k"], 100), (["shifts_by_policy_and_q", "Dstar@0.90", "n"], 17063),
    (["shifts_by_policy_and_q", "B2@0.90", "shift_days"], float("nan")),
    (["feature_rules", "B2@0.90", "snapshot"], "U"), (["preprocessing_and_selected_hyperparameters", "Dstar@0.90", "q"], 0.9126),
    (["runs", "B3@0.90", "status"], "skipped"), (["thresholds", "H2", "relative_improvement"], 0.01),
    (["code_files_sha256"], {}), (["config_sha256"], "abc"),
])
def test_invalid_records_cannot_be_written(tmp_path, path_keys, value):
    rec, _, _ = freeze_fixture(tmp_path)
    _tamper(rec, path_keys, value)
    with pytest.raises(Z.FreezeError):
        Z.write_freeze(tmp_path / "freeze" / "FREEZE.json", rec)


def test_missing_run_needs_an_explicit_failed_status(tmp_path):
    rec, cfgf, pkg = freeze_fixture(tmp_path)
    del rec["runs"]["Dstar@0.9126"]
    with pytest.raises(Z.FreezeError, match="missing"):
        Z.write_freeze(tmp_path / "f1" / "FREEZE.json", rec)                 # silently omitted -> refused
    rec, cfgf, pkg = freeze_fixture(tmp_path)
    rec["runs"]["Dstar@0.9126"] = {"status": "failed", "reason": ""}
    with pytest.raises(Z.FreezeError, match="reason"):
        Z.write_freeze(tmp_path / "f2" / "FREEZE.json", rec)
    rec["runs"]["Dstar@0.9126"] = {"status": "failed", "reason": "all HGB candidates failed to fit"}
    p = tmp_path / "f3" / "FREEZE.json"
    Z.write_freeze(p, rec)
    assert Z.not_evaluable_runs(verify(tmp_path, p, cfgf, pkg)) == ["Dstar@0.9126"]
    rec["runs"]["Extra@0.90"] = {"status": "frozen"}
    with pytest.raises(Z.FreezeError, match="unregistered"):
        Z.write_freeze(tmp_path / "f4" / "FREEZE.json", rec)


def test_scoring_inputs_are_rehashed_not_read_from_the_record(tmp_path):
    rec, cfgf, pkg = freeze_fixture(tmp_path)
    p = tmp_path / "freeze" / "FREEZE.json"
    Z.write_freeze(p, rec)
    other = dict(IDS, E=IDS["E"][:-1] + ["new-order"])
    with pytest.raises(Z.FreezeError, match="partition E"):
        verify(tmp_path, p, cfgf, pkg, ids=other)
    with pytest.raises(Z.FreezeError, match="shift recomputed"):
        verify(tmp_path, p, cfgf, pkg, recompute_shift=lambda key: 6.0 if key != "B3@0.90" else 6.5)
    assert verify(tmp_path, p, cfgf, pkg, recompute_shift=lambda key: 6.0)
    with pytest.raises(Z.FreezeError, match="latest registration"):
        Z.require_frozen(p, tmp_path, cfgf, registered_config_sha="0" * 64, partition_ids=IDS, pkg_dir=pkg)


def test_dependency_code_change_is_caught(tmp_path):
    rec, cfgf, pkg = freeze_fixture(tmp_path)
    p = tmp_path / "freeze" / "FREEZE.json"
    Z.write_freeze(p, rec)
    (pkg / "features.py").write_text("x = 2\n")                               # not a scoring file, but on the feature path
    with pytest.raises(Z.FreezeError, match="features.py"):
        verify(tmp_path, p, cfgf, pkg)


def test_registered_runs_and_thresholds_match_the_config():
    names = {k.split("@")[0] for k in Z.REGISTERED_RUNS}
    assert names <= set(CFG["runs"]) | {"B1c"}
    assert {r["q"] for r in Z.REGISTERED_RUNS.values()} == set(CFG["quantiles"].values())
    assert CFG["models"]["linear_ablation"]["tie_rel"] == Z.THRESHOLDS["ties"]["tie_rel"]
    assert CFG["models"]["linear_ablation"]["adopt_rel"] == Z.THRESHOLDS["ties"]["adopt_rel"]
    assert CFG["bootstrap"]["replicates"] == Z.THRESHOLDS["bootstrap"]["replicates"]
    assert CFG["bootstrap"]["seed"] == Z.THRESHOLDS["bootstrap"]["seed"]
    assert "reference - 1.0" in CFG["metrics"]["practical_rule"] and "1.0 pt" in CFG["metrics"]["practical_rule"]
    assert "1,000 orders" in CFG["metrics"]["monthly_reliability"] and "3.0 pts" in CFG["metrics"]["monthly_reliability"]
    assert ">= 0.5 day" in CFG["hypotheses"]["H1"]["supported_if"] and ">= 0.5 pt" in CFG["hypotheses"]["H1"]["supported_if"]
    assert "g >= 2%" in CFG["hypotheses"]["H2"]["outcomes"]["supported"]
    assert Z.id_sha256(["b", "a"]) == D.id_sha256(["a", "b"])
    import inspect
    assert inspect.signature(M.h1_verdict).parameters["day_thr"].default == Z.THRESHOLDS["H1"]["days"]
    assert inspect.signature(M.h2_outcome).parameters["g_thr"].default == Z.THRESHOLDS["H2"]["relative_improvement"]


# ------------------------------------------------------------------ invalid inputs stop, never become results
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_calibration_refuses_non_finite_labels(bad):
    y = np.arange(100, dtype=float); y[3] = bad                          # sits in the tail the k-th value never reaches
    with pytest.raises(M.InputError, match="labels"):
        M.shift(y, np.zeros(100), 0.90)


@pytest.mark.parametrize("fn", [lambda y, p: M.policy_score(y, p), lambda y, p: M.pinball(y, p, 0.9),
                                lambda y, p: M.pinball_per_order(y, p, 0.9), lambda y, p: M.shift(y, p, 0.5)])
@pytest.mark.parametrize("y,p", [([np.nan, 2.0], [1.0, 2.0]), ([np.inf, 2.0], [1.0, 2.0]), ([1.0, 2.0], [np.nan, 2.0]),
                                 ([1.0, 2.0, 3.0], [1.0, 2.0]), ([], []), ([[1.0, 2.0]], [[1.0, 2.0]])])
def test_scoring_and_calibration_refuse_invalid_inputs(fn, y, p):
    with pytest.raises(M.InputError):
        fn(y, p)


def test_nan_label_is_not_counted_as_covered():
    with pytest.raises(M.InputError):                                    # previously coverage = 100%
        M.policy_score([np.nan, 2], [1, 2])


@pytest.mark.parametrize("q", [0, 1, -0.1, 1.5, np.nan, True, "0.9"])
def test_q_must_be_strictly_between_0_and_1(q):
    with pytest.raises(M.InputError):
        M.shift(np.arange(100.0), np.zeros(100), q)
    with pytest.raises(M.InputError):
        M.pinball([1.0], [1.0], q)


def test_promise_and_bootstrap_refuse_invalid_inputs():
    with pytest.raises(M.InputError):
        M.promise(np.array([]))
    with pytest.raises(M.InputError):
        M.promise(np.array([1.0, 2.0]), float("nan"))
    weeks = np.array([0, 0, 1])
    with pytest.raises(M.InputError):
        M.bootstrap_pooled({"a": np.array([1.0, np.nan, 2.0])}, weeks, np.array([[0, 1]]))
    with pytest.raises(M.InputError):
        M.bootstrap_pooled({"a": np.array([1.0, 2.0])}, weeks, np.array([[0, 1]]))


def test_partition_manifest_has_one_line_per_segment_with_id_hash():
    rng = np.random.default_rng(8)
    pop = frame(400, rng, start="2017-05-01")
    pop["is_late"] = 0
    segs = D.segment_rows(pop, CFG)
    man = D.partition_manifest(segs, CFG).set_index("segment")
    assert list(man.index) == list(D.SEGMENTS)
    assert (man.eligible == man.used + man.excluded).all()
    assert man.loc["V", "id_sha256"] == D.id_sha256(segs["V"]["used"].order_id)
    assert D.id_sha256(["b", "a"]) == D.id_sha256(["a", "b"])


# ------------------------------------------------------------------ selection and verdict rules
def test_tie_set_uses_the_global_minimum_and_is_order_independent():
    prefer = lambda k: (k[0], k[1])                                     # (depth, iterations): shallower, then fewer
    losses = {(3, 800): 1.0000, (2, 400): 1.0009, (2, 200): 1.0012, (3, 100): 1.0005}
    pick, tie = M.select_with_ties(losses, prefer)
    assert pick == (2, 400) and set(tie) == {(3, 800), (2, 400), (3, 100)}   # 1.0012 > 1.001 * L_min
    rev = dict(reversed(list(losses.items())))
    assert M.select_with_ties(rev, prefer)[0] == pick


def test_all_failed_candidates_are_not_evaluable_not_unsupported():
    assert M.select_with_ties({"a": None, "b": float("nan")}, prefer=str) == (M.NOT_EVALUABLE, [])


def test_h1_uses_r0_and_r3_only():
    r0 = {"day_gap": 2.57, "cov_gap": 0.0250, "keep": False}
    # an intermediate step could have moved 0.6 day and come back: only R3 vs R0 counts
    assert M.h1_verdict(r0, {"day_gap": 2.40, "cov_gap": 0.0230, "keep": False})["status"] == \
        "no change reaching the practical thresholds"
    assert M.h1_verdict(r0, {"day_gap": 2.07, "cov_gap": 0.0250, "keep": False})["status"] == "meets H1 standard"
    assert M.h1_verdict(r0, {"day_gap": 2.57, "cov_gap": 0.0300, "keep": False})["status"] == "meets H1 standard"
    assert M.h1_verdict(r0, {"day_gap": 2.57, "cov_gap": 0.0250, "keep": True})["verdict_changed"]
    assert M.h1_verdict(r0, {"day_gap": float("nan"), "cov_gap": 0.0, "keep": False})["status"] == M.NOT_EVALUABLE


def test_h2_threshold_is_relative_not_absolute():
    out = M.h2_outcome(1.500, 1.475, delta_ci_upper=-0.010, cstar_is_c0=False)
    assert np.isclose(out["g"], 0.025 / 1.5) and out["status"] == "below this project's practical standard"   # 1.67%
    assert M.h2_outcome(1.500, 1.470, -0.010, False)["status"] == "meets the pre-set improvement standard"     # 2.0%
    assert M.h2_outcome(1.500, 1.460, 0.005, False)["status"] == \
        "point estimate meets the standard; evidence insufficient"
    rec = M.h2_outcome(1.500, 1.500, 0.0, True)
    assert rec["no_change_selected"] and rec["status"] == "below this project's practical standard"
    assert M.h2_outcome(1.500, float("nan"), 0.0, False)["status"] == M.NOT_EVALUABLE
