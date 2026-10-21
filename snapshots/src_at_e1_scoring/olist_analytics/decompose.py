"""State decomposition of a week-over-week OTD change (spec: docs/metric_dictionary.md).

P_t   = sum_s w_s,t * p_s,t      w = state share of OTD-eligible orders (A+L), p = state OTD
c     = (P0 + P1) / 2            common centre, same for every state

both weeks : performance = (w0 + w1)/2 * (p1 - p0)
             mix         = ((p0 + p1)/2 - c) * (w1 - w0)
entering   : entry       =  w1 * (p1 - c)
exiting    : exit        = -w0 * (p0 - c)

sum of all terms == P1 - P0 (asserted). A state's rate is never filled with 0.
Describes where the change sits, not what caused it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

GROUP = "customer_state_reported"


class NotComparable(ValueError):
    """Raised when either week has no OTD-eligible orders."""


def decompose(sw: pd.DataFrame, w0, w1, group: str = GROUP, min_n_rank: int = 30) -> tuple[pd.DataFrame, dict]:
    """sw: rows (estimated_week, group, A, L). Returns per-group terms and a summary dict."""
    a = sw[sw.estimated_week == w0].set_index(group)
    b = sw[sw.estimated_week == w1].set_index(group)
    n0, n1 = (a.A + a.L), (b.A + b.L)
    N0, N1 = int(n0.sum()), int(n1.sum())
    if N0 == 0 or N1 == 0:
        raise NotComparable(f"no OTD-eligible orders in {'prior' if N0 == 0 else 'current'} week")
    P0, P1 = a.A.sum() / N0, b.A.sum() / N1
    c = (P0 + P1) / 2
    rows = []
    for g in sorted(set(n0[n0 > 0].index) | set(n1[n1 > 0].index)):
        e0, e1 = int(n0.get(g, 0)), int(n1.get(g, 0))
        w_0, w_1 = e0 / N0, e1 / N1
        p_0 = a.A.get(g, 0) / e0 if e0 else np.nan
        p_1 = b.A.get(g, 0) / e1 if e1 else np.nan
        perf = mix = entry = exit_ = 0.0
        if e0 and e1:
            kind = "both"
            perf = (w_0 + w_1) / 2 * (p_1 - p_0)
            mix = ((p_0 + p_1) / 2 - c) * (w_1 - w_0)
        elif e1:
            kind, entry = "entry", w_1 * (p_1 - c)
        else:
            kind, exit_ = "exit", -w_0 * (p_0 - c)
        rows.append({group: g, "status": kind, "eligible_prior": e0, "eligible_current": e1,
                     "share_prior": w_0, "share_current": w_1, "otd_prior": p_0, "otd_current": p_1,
                     "performance": perf, "mix": mix, "entry": entry, "exit": exit_,
                     "total": perf + mix + entry + exit_,
                     "small_sample": min(e0, e1) < min_n_rank})
    out = pd.DataFrame(rows)
    gap = out.total.sum() - (P1 - P0)
    assert abs(gap) < 1e-12, f"decomposition does not reconcile: {gap}"
    summary = {"prior_week": pd.Timestamp(w0), "current_week": pd.Timestamp(w1), "P0": P0, "P1": P1, "c": c,
               "change": P1 - P0, "eligible_prior": N0, "eligible_current": N1, "identity_gap": gap,
               "sum_performance": out.performance.sum(), "sum_mix": out.mix.sum(),
               "sum_entry": out.entry.sum(), "sum_exit": out.exit.sum()}
    return out.sort_values("total").reset_index(drop=True), summary
