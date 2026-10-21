"""Checkpoint 3, steps 3-6 on SYNTHETIC segments: fit -> shift -> freeze -> score, and every way the E entry must
stop BEFORE any E feature, prediction or metric is produced."""
import json
import shutil

import joblib
import numpy as np
import pandas as pd
import pytest

import olist_analytics.e1_data as D
import olist_analytics.e1_freeze as Z
import olist_analytics.e1_models as M
import olist_analytics.e1_pipeline as P
from tests.test_e1_select import CFG, synthetic_runner


def _wire(monkeypatch, out, used, builds):
    monkeypatch.setattr(P, "OUT", out)
    monkeypatch.setattr(P, "load_segments", lambda: (CFG, None, used))
    def build(rows, history, seg, rule):
        builds.append(seg)
        return rows
    monkeypatch.setattr(P, "build", build)
    monkeypatch.setattr(P, "S7", out / "no_stage7")
    monkeypatch.setattr(Z, "CAL_N", len(used["C"]))
    mart = out.parent / "synthetic_mart.csv"; mart.write_text("order_id\nsynthetic\n")
    monkeypatch.setattr(P, "MART", mart, raising=False)


def _s7(E, q2a):
    rng = np.random.default_rng(5)
    return pd.DataFrame({"required_days": D.labels(E).to_numpy(), "Olist_promise": rng.integers(10, 40, len(E)),
                         "B0_state_quantile_0.90": rng.integers(10, 30, len(E)), "Q2_qr_conformal_A_0.90": q2a},
                        index=E.order_id.to_numpy())


@pytest.fixture(scope="module")
def frozen_template(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    # pass 1 (throwaway): learn B2's E promises, so the synthetic "stage-7 Q2A" equals them (deterministic fits)
    tmp0 = tmp_path_factory.mktemp("pass1")
    out0 = synthetic_runner(mp, tmp0)
    used = P.load_segments()[2]
    P.run_select("select")
    _wire(mp, out0, used, [])
    mp.setattr(P, "load_stage7_orders", lambda: _s7(used["E"], np.ones(len(used["E"]), int)))
    fit0 = P.run_fit_freeze()
    b2 = joblib.load(out0 / fit0["record"]["fitted_model_files_sha256"]["B2@0.90"]["path"])
    s7 = _s7(used["E"], M.promise(b2.predict(used["E"]), fit0["record"]["shifts_by_policy_and_q"]["B2@0.90"]["shift_days"]))
    mp.undo()
    # pass 2: the template used by every test
    mp = pytest.MonkeyPatch()
    tmp = tmp_path_factory.mktemp("tmpl")
    out = synthetic_runner(mp, tmp)
    used = P.load_segments()[2]
    P.run_select("select")
    builds = []
    _wire(mp, out, used, builds)
    mp.setattr(P, "load_stage7_orders", lambda: s7)
    fit = P.run_fit_freeze()
    assert "E" not in builds                                           # steps 3-5 never touch E features
    mp.undo()
    return out, used, s7, fit


def setup(monkeypatch, tmp_path, frozen_template, used=None, s7=None):
    src, used0, s7_0, fit = frozen_template
    s7 = s7_0 if s7 is None else s7
    out = tmp_path / "e1"
    shutil.copytree(src, out)
    shutil.rmtree(out / "score", ignore_errors=True)
    used = used or {k: v.copy() for k, v in used0.items()}
    builds = []
    _wire(monkeypatch, out, used, builds)
    monkeypatch.setattr(P, "load_stage7_orders", lambda: s7)
    return out, used, builds, fit


def test_freeze_record_is_complete_and_valid(frozen_template):
    out, used, s7, fit = frozen_template
    rec = json.loads((out / "freeze" / "FREEZE.json").read_text())
    assert set(rec["runs"]) == set(Z.REGISTERED_RUNS) and all(v["status"] == "frozen" for v in rec["runs"].values())
    assert Z.file_sha(out / "freeze" / "FREEZE.json") == (out / "freeze" / "FREEZE.sha256").read_text().split()[0]
    assert fit["summary"]["e_used_for_fit_calibration_selection_or_metrics"] is False
    if rec["preprocessing_and_selected_hyperparameters"]["Cstar@0.90"]["selected_on_V"]["name"] == "C0":
        assert fit["summary"]["cstar_equals_b3_on_C"]


def test_end_to_end_scores_once_and_recomputes_every_shift(monkeypatch, tmp_path, frozen_template):
    out, used, builds, fit = setup(monkeypatch, tmp_path, frozen_template)
    res = P.run_score()
    shifted = sorted(k for k, r in Z.REGISTERED_RUNS.items() if r["shifted"])
    assert res["shifts_recomputed_on_C"] == shifted
    assert (out / "score" / "results.json").exists() and (out / "score" / "e_promises_per_order.csv.gz").exists()
    assert res["consistency"]["B2 shifted promises == stored stage-7 Q2A per order"]
    assert builds.index("E") > builds.index("C")                       # C (shift recomputation) before E
    for h in ("H1", "H2", "H3"):
        assert "status" in res[h]
    with pytest.raises(SystemExit, match="once"):
        P.run_score()


def _assert_stopped_before_e(out, builds):
    assert "E" not in builds
    assert not (out / "score" / "results.json").exists()
    assert not (out / "score" / "e_promises_per_order.csv.gz").exists()
    assert not (out / "score" / "policy_table.csv").exists()


def test_missing_freeze_stops_before_e(monkeypatch, tmp_path, frozen_template):
    out, used, builds, _ = setup(monkeypatch, tmp_path, frozen_template)
    shutil.rmtree(out / "freeze")
    with pytest.raises(Z.FreezeError, match="no freeze"):
        P.run_score()
    _assert_stopped_before_e(out, builds)


def test_changed_model_file_stops_before_e(monkeypatch, tmp_path, frozen_template):
    out, used, builds, fit = setup(monkeypatch, tmp_path, frozen_template)
    p = out / fit["record"]["fitted_model_files_sha256"]["Dstar@0.90"]["path"]
    p.write_bytes(p.read_bytes() + b"x")
    with pytest.raises(Z.FreezeError, match="model file"):
        P.run_score()
    _assert_stopped_before_e(out, builds)


def test_changed_e_sample_stops_before_e(monkeypatch, tmp_path, frozen_template):
    _, used0, _, _ = frozen_template
    used = {k: v.copy() for k, v in used0.items()}
    used["E"] = used["E"].iloc[1:]                                      # one evaluation order fewer
    out, used, builds, _ = setup(monkeypatch, tmp_path, frozen_template, used)
    with pytest.raises(Z.FreezeError, match="partition E"):
        P.run_score()
    _assert_stopped_before_e(out, builds)


def test_shift_mismatch_on_c_stops_before_e(monkeypatch, tmp_path, frozen_template):
    _, used0, _, _ = frozen_template
    used = {k: v.copy() for k, v in used0.items()}
    c = used["C"]
    used["C"] = c.assign(order_delivered_customer_date=c.order_delivered_customer_date + pd.Timedelta(days=5))  # same ids, other labels
    out, used, builds, _ = setup(monkeypatch, tmp_path, frozen_template, used)
    with pytest.raises(Z.FreezeError, match="shift recomputed"):
        P.run_score()
    _assert_stopped_before_e(out, builds)


def test_edited_freeze_shift_stops_before_e(monkeypatch, tmp_path, frozen_template):
    out, used, builds, _ = setup(monkeypatch, tmp_path, frozen_template)
    f = out / "freeze" / "FREEZE.json"
    rec = json.loads(f.read_text()); rec["shifts_by_policy_and_q"]["Dstar@0.90"]["shift_days"] += 1.0
    f.write_text(json.dumps(rec, indent=2, sort_keys=True))
    (out / "freeze" / "FREEZE.sha256").write_text(Z.file_sha(f) + "  FREEZE.json\n")   # even with the hash rewritten
    with pytest.raises(Z.FreezeError, match="shift recomputed"):
        P.run_score()
    _assert_stopped_before_e(out, builds)


def test_fit_freeze_refuses_a_blocked_selection(monkeypatch, tmp_path, frozen_template):
    out, used, builds, _ = setup(monkeypatch, tmp_path, frozen_template)
    (out / "select" / "qa" / "RELEASE_BLOCKED.json").write_text("[]")
    shutil.rmtree(out / "final")
    with pytest.raises(SystemExit, match="block marker"):
        P.run_fit_freeze()


# ------------------------------------------------------------------ input CONTENT (post-hoc hardening, review 2026-10-20)
def test_freeze_records_input_identity(frozen_template):
    out, used, s7, fit = frozen_template
    assert set(fit["record"]["input_identity"]) == set(Z.INPUT_KEYS)


def test_same_ids_changed_e_labels_stop_before_e(monkeypatch, tmp_path, frozen_template):
    _, used0, _, _ = frozen_template
    used = {k: v.copy() for k, v in used0.items()}
    used["E"] = used["E"].assign(order_delivered_customer_date=used["E"].order_delivered_customer_date + pd.Timedelta(days=100))
    out, used, builds, _ = setup(monkeypatch, tmp_path, frozen_template, used)
    with pytest.raises(Z.FreezeError, match="rows_E"):
        P.run_score()
    _assert_stopped_before_e(out, builds)


def test_same_ids_changed_e_feature_stops_before_e(monkeypatch, tmp_path, frozen_template):
    _, used0, _, _ = frozen_template
    used = {k: v.copy() for k, v in used0.items()}
    used["E"] = used["E"].assign(distance_km=used["E"].distance_km * 2)
    out, used, builds, _ = setup(monkeypatch, tmp_path, frozen_template, used)
    with pytest.raises(Z.FreezeError, match="rows_E"):
        P.run_score()
    _assert_stopped_before_e(out, builds)


def test_changed_b0_reference_stops_before_e(monkeypatch, tmp_path, frozen_template):
    _, _, s7, _ = frozen_template
    out, used, builds, _ = setup(monkeypatch, tmp_path, frozen_template,
                                 s7=s7.assign(**{"B0_state_quantile_0.90": s7["B0_state_quantile_0.90"] + 100}))
    with pytest.raises(Z.FreezeError, match="stage7_reference"):
        P.run_score()
    _assert_stopped_before_e(out, builds)


def test_canonical_hash_ignores_row_and_column_order_but_not_values():
    df = pd.DataFrame({"order_id": ["b", "a"], "x": [1.0, 2.0], "t": pd.to_datetime(["2018-01-01", "2018-01-02"])})
    h = Z.canonical_frame_sha(df)
    assert h == Z.canonical_frame_sha(df.iloc[::-1][["t", "x", "order_id"]])
    assert h != Z.canonical_frame_sha(df.assign(x=[1.0, 2.0000001]))


def test_freeze_without_any_input_identity_is_refused(monkeypatch, tmp_path, frozen_template):
    out, used, builds, _ = setup(monkeypatch, tmp_path, frozen_template)
    f = out / "freeze" / "FREEZE.json"
    rec = json.loads(f.read_text()); rec.pop("input_identity")
    f.write_text(json.dumps(rec, indent=2, sort_keys=True))
    (out / "freeze" / "FREEZE.sha256").write_text(Z.file_sha(f) + "  FREEZE.json\n")
    with pytest.raises(Z.FreezeError, match="no input identity"):
        P.run_score()
    _assert_stopped_before_e(out, builds)


# ------------------------------------------------------------------ addendum binding (review 2026-10-20 evening)
def _legacy_with_addendum(monkeypatch, tmp_path, frozen_template, binding="actual", body=None):
    """A freeze WITHOUT inline input identity (like the historical one) plus a post-hoc addendum."""
    out, used, builds, fit = setup(monkeypatch, tmp_path, frozen_template)
    f = out / "freeze" / "FREEZE.json"
    rec = json.loads(f.read_text()); ident = rec.pop("input_identity")
    f.write_text(json.dumps(rec, indent=2, sort_keys=True))
    (out / "freeze" / "FREEZE.sha256").write_text(Z.file_sha(f) + "  FREEZE.json\n")
    add = out / "freeze" / P.INPUT_ADDENDUM
    if body is not None:
        add.write_text(body)
    else:
        doc = {"post_hoc": True, "input_identity": ident,
               "applies_to_freeze_sha256": Z.file_sha(f) if binding == "actual" else binding}
        if binding is None:
            doc.pop("applies_to_freeze_sha256")
        add.write_text(json.dumps(doc))
    return out, builds


def test_addendum_bound_to_this_freeze_is_accepted(monkeypatch, tmp_path, frozen_template):
    out, builds = _legacy_with_addendum(monkeypatch, tmp_path, frozen_template)
    P.run_score()                                                          # positive control
    assert (out / "score" / "results.json").exists()


@pytest.mark.parametrize("case,kw", [
    ("wrong binding (all zeros)", {"binding": "0" * 64}),
    ("missing binding", {"binding": None}),
    ("malformed: not JSON", {"body": "{not json"}),
    ("malformed: a list", {"body": "[1, 2]"}),
    ("malformed: no input identity", {"body": json.dumps({"post_hoc": True, "applies_to_freeze_sha256": "0" * 64})}),
])
def test_bad_addendum_stops_before_e(monkeypatch, tmp_path, frozen_template, case, kw):
    out, builds = _legacy_with_addendum(monkeypatch, tmp_path, frozen_template, **kw)
    with pytest.raises(Z.FreezeError):
        P.run_score()
    _assert_stopped_before_e(out, builds)
