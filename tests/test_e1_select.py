"""Checkpoint-3 step 2 (selection on F0 / V): adoption rule, ties, failures, fallback retry. Synthetic only."""
import numpy as np
import pandas as pd
import pytest

import olist_analytics.e1_data as D
import olist_analytics.e1_models as M
import olist_analytics.e1_pipeline as P

CFG = D.cfg()
SPEC, ABL, HGB = CFG["models"]["linear_registered"], CFG["models"]["linear_ablation"], CFG["models"]["hgb"]
yV = np.arange(1.0, 51.0)


class Fixed:
    def __init__(self, marker):
        self.marker = marker
    def predict(self, X):
        return np.full(len(yV), float(self.marker))


def linear_world(monkeypatch, losses, fail=()):
    """losses: {(dow_categorical, target, alpha): V loss}. A fitter whose model 'predicts' a marker; int_loss maps it."""
    keys = list(losses)
    monkeypatch.setattr(P, "int_loss", lambda y, p, q: losses[keys[int(p[0])]])
    def fitter(spec, q, X, y, *, fallback, dow_categorical, target, alpha):
        k = (dow_categorical, target, alpha)
        if k in fail:
            raise P.FitFailed("synthetic failure")
        return Fixed(keys.index(k)), {"solver": "highs", "retry": False}
    return fitter


def run_linear(monkeypatch, losses, fail=()):
    return P.linear_selection(SPEC, ABL, "highs-ipm", None, None, None, yV, fitter=linear_world(monkeypatch, losses, fail))


BASE = {(False, "log1p", 0.0): 1.000, (True, "log1p", 0.0): 0.995,          # C1 only 0.5% better -> rejected
        (False, "days", 0.0): 0.970,                                         # C2 3% better -> adopted
        (False, "days", 0.001): 0.9650, (False, "days", 0.01): 0.9655, (False, "days", 0.1): 0.990}


def test_one_percent_rule_and_alpha_tie_pick(monkeypatch):
    pick, log = run_linear(monkeypatch, BASE)
    d = log.set_index("step")
    assert not d.loc["C1", "adopted"] and "rejected" in d.loc["C1", "decision"]
    assert d.loc["C2", "adopted"]
    # C3 grid follows the C2 winner's target (days); 0.9650 and 0.9655 tie (<= 1.001 x min) -> larger alpha 0.01
    assert d.loc["C3 alpha=0.01", "in_tie_set"] and d.loc["C3 alpha=0.001", "in_tie_set"]
    assert not d.loc["C3 alpha=0.1", "in_tie_set"]
    # the pick (0.9655) is only 0.46% below C2 (0.970) -> rejected, C2 stays
    assert not d.loc["C3 alpha=0.01", "adopted"] and pick["name"] == "C2"
    assert pick["setting"] == {"dow_categorical": False, "target": "days", "alpha": 0.0}
    assert log.selected.sum() == 1 and d.loc["C2", "selected"]


def test_alpha_adopted_when_it_clears_one_percent(monkeypatch):
    losses = dict(BASE); losses[(False, "days", 0.01)] = 0.950; losses[(False, "days", 0.001)] = 0.9505
    pick, _ = run_linear(monkeypatch, losses)
    assert pick["name"] == "C3 alpha=0.01" and pick["setting"]["alpha"] == 0.01


def test_log1p_target_uses_its_own_alpha_grid(monkeypatch):
    losses = {(False, "log1p", 0.0): 1.0, (True, "log1p", 0.0): 1.1, (False, "days", 0.0): 1.2,
              (False, "log1p", 0.0001): 1.0, (False, "log1p", 0.001): 1.0, (False, "log1p", 0.01): 1.0}
    pick, log = run_linear(monkeypatch, losses)
    assert set(log.step) >= {"C3 alpha=0.0001", "C3 alpha=0.001", "C3 alpha=0.01"} and pick["name"] == "C0"


def test_failed_step_is_rejected_and_recorded(monkeypatch):
    pick, log = run_linear(monkeypatch, BASE, fail={(True, "log1p", 0.0)})
    d = log.set_index("step")
    assert d.loc["C1", "status"].startswith("failed") and not d.loc["C1", "adopted"]
    assert np.isnan(d.loc["C1", "v_pinball_int"]) and pick["name"] == "C2"


def test_failed_registered_start_is_not_evaluable(monkeypatch):
    pick, log = run_linear(monkeypatch, BASE, fail={(False, "log1p", 0.0)})
    assert pick == M.NOT_EVALUABLE and len(log) == 1


def test_fallback_solver_is_one_labelled_retry(monkeypatch):
    calls = []
    class Fake:
        def __init__(self, spec, q, solver, **kw):
            self.solver = solver
        def fit(self, X, y):
            calls.append(self.solver)
            if self.solver == "highs":
                raise ValueError("highs failed")
            return self
    monkeypatch.setattr(M, "LinearModel", Fake)
    m, info = P.fit_linear(SPEC, 0.9, None, None, dow_categorical=False, target="log1p", alpha=0.0, fallback="highs-ipm")
    assert calls == ["highs", "highs-ipm"] and info["retry"] and info["solver"] == "highs-ipm"
    class AlwaysFail(Fake):
        def fit(self, X, y):
            calls.append(self.solver); raise ValueError("no")
    monkeypatch.setattr(M, "LinearModel", AlwaysFail)
    calls.clear()
    with pytest.raises(P.FitFailed):
        P.fit_linear(SPEC, 0.9, None, None, dow_categorical=False, target="log1p", alpha=0.0, fallback="highs-ipm")
    assert calls == ["highs", "highs-ipm"]                                   # exactly one retry, no other settings


def hgb_world(monkeypatch, losses, fail=()):
    keys = list(losses)
    monkeypatch.setattr(P, "int_loss", lambda y, p, q: losses[keys[int(p[0])]])
    def fitter(spec, hgb, q, X, y, d, it):
        if (d, it) in fail:
            raise RuntimeError("synthetic failure")
        return Fixed(keys.index((d, it)))
    return fitter


def test_hgb_tie_set_prefers_shallower_then_fewer_iterations(monkeypatch):
    losses = {(2, 100): 1.10, (2, 200): 1.0008, (2, 400): 1.0004, (2, 800): 1.02,
              (3, 100): 1.05, (3, 200): 1.0000, (3, 400): 1.0011, (3, 800): 1.03}
    pick, df = P.hgb_selection(SPEC, HGB, None, None, None, yV, fitter=hgb_world(monkeypatch, losses))
    assert pick["setting"] == {"max_depth": 2, "max_iter": 200}                 # tie set {(3,200),(2,400),(2,200)}
    assert df.in_tie_set.sum() == 3 and df.selected.sum() == 1 and len(df) == 8


def test_hgb_failure_recorded_and_all_failed_not_evaluable(monkeypatch):
    losses = {(d, it): 1.0 + 0.01 * i for i, (d, it) in enumerate([(2, 100), (2, 200), (2, 400), (2, 800),
                                                                    (3, 100), (3, 200), (3, 400), (3, 800)])}
    pick, df = P.hgb_selection(SPEC, HGB, None, None, None, yV, fitter=hgb_world(monkeypatch, losses, fail={(2, 100)}))
    assert df.loc[0, "status"].startswith("failed") and pick["setting"] == {"max_depth": 2, "max_iter": 200}
    pick, df = P.hgb_selection(SPEC, HGB, None, None, None, yV, fitter=hgb_world(monkeypatch, losses, fail=set(losses)))
    assert pick == M.NOT_EVALUABLE and not df.selected.any()


def test_residual_flag_needs_500_orders_and_3_points():
    n = 2000
    y = np.r_[np.full(1000, 5.0), np.full(1000, 5.0)]
    d = np.r_[np.full(1000, 10.0), np.r_[np.full(880, 10.0), np.full(120, 1.0)]]     # second half 88% covered
    purchase = pd.Series(pd.to_datetime(["2017-07-10"] * 1000 + ["2017-08-10"] * 1000))
    df, overall = P.residual_diagnostics(y, d, purchase, np.linspace(1, 20, n), np.zeros(n))
    m = df[df.grouping == "purchase month"].set_index("group")
    assert np.isclose(overall, 0.94) and m.loc["2017-08", "flag"] and m.loc["2017-07", "flag"]   # +/-6 pts


def test_runtime_self_check_passes_on_fixed_code():
    assert all(r["pass"] for r in P.runtime_self_check())


def test_selected_settings_can_be_passed_back_to_the_fitters():
    """Attempt 1 of the selection run aborted here: the refit for residual diagnostics passed the selected HGB
    setting as keywords. Both fitters must accept their selection dicts as keywords."""
    from tests.test_e1 import frame
    rng = np.random.default_rng(3)
    X = frame(400, rng)
    y = (X.order_delivered_customer_date.dt.normalize() - X.order_purchase_timestamp.dt.normalize()).dt.days.to_numpy(float)
    m = P.fit_hgb(SPEC, HGB, 0.9, X, y, **{"max_depth": 2, "max_iter": 10})
    assert np.isfinite(m.predict(X)).all()
    lm, info = P.fit_linear(SPEC, 0.9, X, y, fallback="highs-ipm", **{"dow_categorical": True, "target": "days", "alpha": 0.01})
    assert np.isfinite(lm.predict(X)).all() and info["solver"] in ("highs", "highs-ipm")


# ------------------------------------------------------------------ publish order (review of step 2)
def _checks(ok=True):
    return pd.DataFrame([{"check": "a", "expected": 1, "actual": 1 if ok else 2}])


def _stage(tmp_path):
    st = tmp_path / "select"; (st / "qa").mkdir(parents=True)
    (st / "RUN_REGISTRATION.json").write_text("{}")
    return st


def test_failed_post_check_leaves_no_official_file(tmp_path):
    from olist_analytics.gate import ReleaseBlocked
    st = _stage(tmp_path)
    (st / "selection.json").write_text('{"stale": true}')                 # even a stale file must go
    with pytest.raises(ReleaseBlocked):
        P.publish(st, _checks(ok=False), {"x": 1})
    assert not (st / "selection.json").exists() and (st / "qa" / "RELEASE_BLOCKED.json").exists()
    with pytest.raises(SystemExit, match="block marker"):
        P.require_published(st)


def test_passing_checks_publish_and_downstream_accepts(tmp_path):
    from olist_analytics import e1_freeze as Z
    st = _stage(tmp_path)
    P.publish(st, _checks(), {"registration_sha256": Z.file_sha(st / "RUN_REGISTRATION.json")})
    assert P.require_published(st)
    (st / "RUN_REGISTRATION.json").write_text('{"edited": 1}')
    with pytest.raises(SystemExit, match="changed"):
        P.require_published(st)


def test_unpublished_stage_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="missing"):
        P.require_published(_stage(tmp_path))


def test_per_order_file_reproduces_logged_losses(monkeypatch):
    keep = {}
    real_int_loss = P.int_loss
    rng = np.random.default_rng(1)
    preds = {"C0": rng.uniform(1, 40, len(yV)), "D3": rng.uniform(1, 40, len(yV))}
    df = P.per_order_long([f"o{i}" for i in range(len(yV))], yV, preds, 0.90)
    assert list(df.columns) == ["order_id", "candidate", "q", "actual_days", "prediction_unrounded", "promise_days"]
    rec = P.losses_from_per_order(df).set_index("candidate")
    for k, v in preds.items():
        assert rec.loc[k, "v_pinball_int"] == pytest.approx(real_int_loss(yV, v, 0.90), abs=1e-12)


def test_selection_keeps_every_successful_candidate_prediction(monkeypatch):
    keep = {}
    P.linear_selection(SPEC, ABL, "highs-ipm", None, None, None, yV,
                       fitter=linear_world(monkeypatch, BASE, fail={(True, "log1p", 0.0)}), keep=keep)
    assert set(keep) == {"C0", "C2", "C3 alpha=0.001", "C3 alpha=0.01", "C3 alpha=0.1"}   # failed C1 has none


# ------------------------------------------------------------------ the runner itself, on synthetic segments
def synthetic_runner(monkeypatch, tmp_path, fail_post=False):
    from tests.test_e1 import frame
    from olist_analytics import e1_freeze as Z
    rng = np.random.default_rng(11)
    used = {s: frame(n, rng, start=st).assign(order_id=lambda d, s=s: [f"{s}{i}" for i in range(len(d))])
            for s, n, st in [("F0", 600, "2017-01-05"), ("V", 300, "2017-07-02"), ("F", 900, "2017-01-05"),
                             ("C", 300, "2017-10-02"), ("E", 300, "2018-04-02")]}
    out = tmp_path / "e1"; (out / "prep").mkdir(parents=True)
    (out / "PREREGISTRATION_SHA256.txt").write_text(Z.file_sha(P.CFG_PATH) + "  v3\n")
    pd.DataFrame([{"segment": s, "used": len(v), "id_sha256": D.id_sha256(v.order_id)} for s, v in used.items()]) \
        .to_csv(out / "prep" / "partition_manifest.csv", index=False)
    monkeypatch.setattr(P, "OUT", out)
    mart = tmp_path / "synthetic_mart.csv"; mart.write_text("order_id\nsynthetic\n")
    monkeypatch.setattr(P, "MART", mart, raising=False)                                 # never the real mart
    monkeypatch.setattr(P, "load_segments", lambda: (CFG, None, used))
    monkeypatch.setattr(P, "build", lambda rows, history, seg, rule: rows)
    if fail_post:                                   # code fingerprint "changes" between registration and the end
        real = Z.code_fingerprint
        calls = {"n": 0}
        def fp(pkg):
            calls["n"] += 1
            c, f = real(pkg)
            return (c if calls["n"] == 1 else "0" * 64), f
        monkeypatch.setattr(Z, "code_fingerprint", fp)
    return out


def test_runner_failure_after_fitting_publishes_nothing(monkeypatch, tmp_path):
    from olist_analytics.gate import ReleaseBlocked
    out = synthetic_runner(monkeypatch, tmp_path, fail_post=True)
    import inspect
    kw = {"out_name": "select"} if "out_name" in inspect.signature(P.run_select).parameters else {}
    with pytest.raises(ReleaseBlocked):
        P.run_select(**kw)                          # same call works on the step-2 version (no arguments)
    st = out / "select"
    assert not (st / "selection.json").exists()
    assert (st / "qa" / "RELEASE_BLOCKED.json").exists() and (st / "RUN_REGISTRATION.json").exists()
    with pytest.raises(SystemExit):
        P.require_published(st)


def test_runner_end_to_end_and_reproduction(monkeypatch, tmp_path):
    out = synthetic_runner(monkeypatch, tmp_path)
    r = P.run_select("select")
    st = out / "select"
    assert P.require_published(st)["linear"]["setting"] == r["out"]["linear"]["setting"]
    po = pd.read_csv(st / "v_predictions_per_order.csv.gz")
    assert po.candidate.nunique() == 14 and len(po) == 14 * 300
    rec = P.losses_from_per_order(po).set_index("candidate")
    lin = pd.read_csv(st / "linear_ablation.csv").set_index("step")
    assert np.allclose(rec.loc[lin.index, "v_pinball_int"], lin.v_pinball_int, atol=1e-12)
    with pytest.raises(SystemExit, match="written once"):
        P.run_select("select")                                          # never overwritten
    r2 = P.run_select("select_repro1", reproduces="select")
    assert r2["comparison"].abs_diff.max() < 1e-9 and (out / "select_repro1" / "selection.json").exists()
