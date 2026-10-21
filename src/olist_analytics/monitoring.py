"""Stage 7 part 3: when should a frozen promised-date policy be reviewed?

Two registered alarm rules on weekly purchase cohorts (alarms trigger human review only):
  threshold : weekly coverage < target - 5 pts for 2 consecutive weeks, each with >= 200 orders
  CUSUM     : Bernoulli CUSUM on misses, p0 = 1 - target, p1 = p0 + 0.05, per-order log-likelihood ratios
              summed by week; h chosen by simulation for an in-control average run length of ~52 weeks
Readings of the registered text are logged in docs/DATE_POLICY_DECISIONS.md (M1-M8, deviation D1).

With 1,200 orders a week the registered ARL is unreachable and h = 0 is used. At h = 0 the statistic never carries
over: a positive week alarms and resets, a non-positive week floors at 0. The rule is then a single-week
log-likelihood-ratio threshold (memoryless), NOT a cumulative CUSUM. Exact in-control ARLs for both rules are in
`nominal_arl_*` below; they differ by many orders of magnitude, so the two rules are not compared at equal
false-alarm burden.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import binom


# ------------------------------------------------------------------ weekly cohorts
def weekly_cohorts(purchase: pd.Series, required: pd.Series, promised: pd.Series) -> pd.DataFrame:
    """One row per Monday-start purchase week. A week is final once its largest promise has passed (+1 day)."""
    wk = purchase.dt.normalize() - pd.to_timedelta(purchase.dt.weekday, unit="D")
    d = pd.DataFrame({"week": wk.values, "req": np.asarray(required), "prom": np.asarray(promised)})
    d["miss"] = d.req > d.prom
    g = d.groupby("week").agg(orders=("miss", "size"), misses=("miss", "sum"), max_promise=("prom", "max"),
                              median_required=("req", "median")).reset_index()
    g["coverage"] = 1 - g.misses / g.orders
    # last purchase day of the week = Sunday (week + 6); a miss is known the day after its promise date
    g["final_at"] = g.week + pd.Timedelta(days=6) + pd.to_timedelta(g.max_promise + 1, unit="D")
    return g


# ------------------------------------------------------------------ alarm rules
def cusum_weights(p0: float, p1: float) -> tuple[float, float]:
    """Log-likelihood-ratio increment for one miss and for one covered order."""
    return float(np.log(p1 / p0)), float(np.log((1 - p1) / (1 - p0)))


def cusum(misses, orders, p0: float, p1: float, h: float) -> tuple[np.ndarray, np.ndarray]:
    """Weekly Bernoulli CUSUM. Returns (statistic after each week, alarm flags); resets to 0 after an alarm."""
    a, b = cusum_weights(p0, p1)
    s, stat, alarm = 0.0, [], []
    for m, n in zip(np.asarray(misses, float), np.asarray(orders, float)):
        s = max(0.0, s + m * a + (n - m) * b)
        hit = s > h
        stat.append(s)
        alarm.append(hit)
        if hit:
            s = 0.0
    return np.array(stat), np.array(alarm, bool)


def threshold_alarms(coverage, orders, target: float, pts: float = 5.0, run: int = 2, min_orders: int = 200) -> np.ndarray:
    """Alarm on the week that completes `run` consecutive low weeks; a small week breaks the run; reset after an alarm."""
    low = (np.asarray(coverage) < target - pts / 100) & (np.asarray(orders) >= min_orders)
    count, out = 0, []
    for x in low:
        count = count + 1 if x else 0
        out.append(count >= run)
        if count >= run:
            count = 0
    return np.array(out, bool)


def single_week_alarm_misses(p0: float, p1: float, n: int) -> int:
    """Smallest weekly miss count whose LLR sum is > 0 (the h = 0 alarm condition)."""
    a, b = cusum_weights(p0, p1)
    m = int(np.floor(-n * b / (a - b))) + 1
    return m if m * a + (n - m) * b > 0 else m + 1


def nominal_arl_single_week(p0: float, p1: float, n: int, p_true: float | None = None) -> dict:
    """Exact ARL of the h = 0 rule (memoryless: geometric). p_true defaults to p0 (in control)."""
    m = single_week_alarm_misses(p0, p1, n)
    q = float(binom.sf(m - 1, n, p0 if p_true is None else p_true))
    a, b = cusum_weights(p0, p1)
    return {"alarm_if_misses_at_least": m, "llr_boundary_miss_rate": -b / (a - b),
            "weekly_alarm_prob": q, "arl_weeks": 1 / q if q > 0 else float("inf")}


def nominal_arl_threshold(target: float, n: int, pts: float = 5.0, run: int = 2, p_true: float | None = None) -> dict:
    """Exact ARL of the threshold rule with reset (waiting time for `run` consecutive low weeks)."""
    m = int(np.floor(n * (1 - target + pts / 100) + 1e-9)) + 1          # coverage < target - pts  <=>  misses >= m
    q = float(binom.sf(m - 1, n, (1 - target) if p_true is None else p_true))
    if q <= 0:
        arl = float("inf")
    elif q >= 1:
        arl = float(run)                      # every week crosses: the alarm comes at week `run`
    else:
        arl = (1 - q ** run) / ((1 - q) * q ** run)
    return {"low_week_if_misses_at_least": m, "weekly_low_prob": q, "arl_weeks": arl}


# ------------------------------------------------------------------ calibration of h
def first_alarm_weeks(increments: np.ndarray, h: float) -> np.ndarray:
    """increments: (runs, weeks). Week (1-based) of the first alarm per run, or weeks + 1 when none."""
    runs, weeks = increments.shape
    s = np.zeros(runs)
    first = np.full(runs, weeks + 1)
    alive = np.ones(runs, bool)
    for t in range(weeks):
        s = np.maximum(0.0, s + increments[:, t])
        hit = alive & (s > h)
        first[hit] = t + 1
        alive &= ~hit
        if not alive.any():
            break
    return first


def calibrate_h(p0: float, p1: float, n: int, target_arl: float, rng: np.random.Generator,
                runs: int = 10_000, cap: int = 1_000) -> dict:
    """Bisection on h so the in-control (Bernoulli p0) average run length is closest to target_arl.
    The simulated value is a restricted mean (at most cap + 1), so a target above cap + 1 is refused."""
    if target_arl > cap + 1:
        raise ValueError(f"target ARL {target_arl} cannot be reached by a mean restricted to cap + 1 = {cap + 1} weeks")
    a, b = cusum_weights(p0, p1)
    m = rng.binomial(n, p0, size=(runs, cap))
    inc = m * a + (n - m) * b
    arl = lambda h: float(first_alarm_weeks(inc, h).mean())
    lo, hi = 0.0, 1.0
    for _ in range(64):                       # bounded search for an upper bracket
        if arl(hi) >= target_arl:
            break
        hi *= 2
    else:
        raise ValueError("no h with restricted mean run length >= target found")
    for _ in range(40):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if arl(mid) < target_arl else (lo, mid)
    h = min((lo, hi), key=lambda x: abs(arl(x) - target_arl))
    fa = first_alarm_weeks(inc, h)
    # runs with no alarm by `cap` are counted as cap + 1: this is a RESTRICTED mean, not the full ARL
    return {"h": h, "restricted_mean_run_length_weeks": float(fa.mean()), "cap_weeks": cap, "runs": runs,
            "censored_runs": int((fa > cap).sum()), "censored_share": float((fa > cap).mean())}


# ------------------------------------------------------------------ simulation
def multiplier(scenario: str, week: int) -> float:
    """week is 1-based. Registered scenarios (reading M4)."""
    if scenario == "none":
        return 1.0
    if scenario == "sudden":
        return 1.2 if week >= 9 else 1.0
    if scenario == "gradual":
        return 1.0 + 0.02 * (week - 4) if week >= 5 else 1.0
    if scenario == "transient":
        return 1.3 if week in (9, 10) else 1.0
    raise ValueError(scenario)


CHANGE_WEEK = {"none": None, "sudden": 9, "gradual": 5, "transient": 9}


def shifted(required: np.ndarray, m: float) -> np.ndarray:
    return np.floor(np.asarray(required, float) * m + 0.5).astype(int) if m != 1.0 else np.asarray(required)


def simulate(required: np.ndarray, promised: np.ndarray, scenario: str, *, p0: float, p1: float, h: float, target: float,
             weeks: int, n: int, reps: int, rng: np.random.Generator, week_pools: list[np.ndarray] | None = None) -> pd.DataFrame:
    """Bootstrap orders (or, with week_pools, orders from one randomly drawn historical week per simulated week).
    Returns one row per (rep, week): misses, coverage, max promise, CUSUM / threshold alarms."""
    a, b = cusum_weights(p0, p1)
    req, prom = np.asarray(required), np.asarray(promised)
    s = np.zeros(reps)
    run = np.zeros(reps, int)
    rows = []
    for w in range(1, weeks + 1):
        if week_pools is None:
            idx = rng.integers(0, len(req), size=(reps, n))
        else:
            pick = rng.integers(0, len(week_pools), size=reps)
            idx = np.stack([week_pools[k][rng.integers(0, len(week_pools[k]), size=n)] for k in pick])
        r, p = shifted(req[idx], multiplier(scenario, w)), prom[idx]
        miss = (r > p).sum(axis=1)
        s = np.maximum(0.0, s + miss * a + (n - miss) * b)
        c_alarm = s > h
        s[c_alarm] = 0.0
        cov = 1 - miss / n
        low = cov < target - 0.05
        run = np.where(low, run + 1, 0)
        t_alarm = run >= 2
        run[t_alarm] = 0
        rows.append(pd.DataFrame({"rep": np.arange(reps), "week": w, "misses": miss, "coverage": cov,
                                  "max_promise": p.max(axis=1), "cusum_alarm": c_alarm, "threshold_alarm": t_alarm}))
    return pd.concat(rows, ignore_index=True)


def summarize(sim: pd.DataFrame, scenario: str, weeks: int) -> list[dict]:
    """Registered metrics per rule: false alarms per year, detection delay (weeks and calendar days), missed share."""
    cw = CHANGE_WEEK[scenario]
    out = []
    for rule in ("cusum", "threshold"):
        col = f"{rule}_alarm"
        rec = {"scenario": scenario, "rule": rule, "change_week": cw,
               "mean_coverage": float(sim.coverage.mean()),
               "mean_coverage_after_change": float(sim[sim.week >= cw].coverage.mean()) if cw else None}
        pre = sim[sim.week < cw] if cw else sim
        pre_weeks = (cw - 1) if cw else weeks
        rec["false_alarms_per_year"] = float(pre.groupby("rep")[col].sum().mean() * 52 / pre_weeks) if pre_weeks else None
        if cw:
            post = sim[(sim.week >= cw) & sim[col]].sort_values("week").groupby("rep").first()
            reps = sim.rep.nunique()
            delay_w = post.week - cw
            # calendar: change starts on the Monday of week cw; the alarm week is final on its Sunday + max promise + 1
            delay_d = (post.week - cw) * 7 + 6 + post.max_promise + 1
            rec.update({"detected_share": len(post) / reps, "missed_detection_share": 1 - len(post) / reps,
                        "median_delay_weeks": float(delay_w.median()) if len(post) else None,
                        "median_delay_days_to_final": float(delay_d.median()) if len(post) else None})
        out.append(rec)
    return out


def dispersion_ratio(weekly: pd.DataFrame, min_orders: int = 200) -> float:
    """Observed variance of weekly miss rates / the average binomial variance. 1 = pure order-level noise."""
    w = weekly[weekly.orders >= min_orders]
    p = w.misses.sum() / w.orders.sum()
    return float(w.coverage.var(ddof=1) / (p * (1 - p) / w.orders).mean())
