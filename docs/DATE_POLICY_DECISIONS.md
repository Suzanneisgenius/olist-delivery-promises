# Stage 7 decision log

Every change to `config/date_policy.yaml` after it was first written, with time (UTC), reason and whether any
policy result had been seen. Stage 7 is an exploratory extension: stages 1–6 had already inspected these data.

| Time (UTC) | Change | Results seen before? | Config SHA-256 |
|---|---|---|---|
| 2026-10-14 (first write) | Pre-registered design: windows, policies, targets, decision rules, monitoring rules | No (only the stage-7 phase-0 descriptive checks: promise vs actual days, slack, calibration-window observability) | 84930561a08cf08a7a64e9b4936054864c008939b2d087bd92153b7a4370eb42 |
| 2026-10-14T05:40:54Z | Added `descriptive_curves` (trade-off sweeps, incl. a uniform shift of the existing promise). Descriptive only; no decision rule uses them | No | 9c1ff876fb1777719a95cdb606b1f78be7989441b328a7b664dc8076a95b4747 |

## Part 3 (monitoring): how the registered text is read

Written 2026-10-14T05:56Z, before any part-3 code was run. These are readings of the registered `monitoring` block, not config
changes, so the config SHA-256 is unchanged. Parts 1–2 results **had** been seen (they choose which policy is monitored).

| # | Registered text | Reading used |
|---|---|---|
| M1 | "the frozen policy", "target" | Monitored policy = the one parts 1–2 kept: B0 (per-state quantile) at target 0.90, so p0 = 0.10. Olist's own promise is monitored against the matched target (its calibration-A coverage, 0.9126). |
| M2 | "purchase week" | Monday-start purchase week. Final at week end + the largest promise in that week + 1 day. |
| M3 | threshold / CUSUM alarms | After an alarm the counter (threshold rule) or the CUSUM statistic resets to 0, so repeated alarms are counted separately. |
| M4 | "required_days x 1.2" etc. | Shifted days = round-half-up(required_days × multiplier). Gradual: multiplier 1 + 0.02 × (week − 4) from week 5. Transient: × 1.3 in weeks 9–10 only. |
| M5 | "h set by simulation" | Bernoulli misses at p0 with 1,200 orders/week, 10,000 runs, cap 1,000 weeks; h chosen by bisection so the in-control ARL is closest to 52 weeks. |
| M6 | metrics | Detection = first alarm in or after the change week; alarms before it are false alarms. Missed = no alarm by week 30. Delay reported in purchase weeks and in calendar days (alarm-week finality date − change start). False alarms per year = alarms in the "none" scenario × 52 / 30. |
| M7 | — (not registered; exploratory, no decision uses it) | (a) Over-dispersion check: observed week-to-week variance of misses vs binomial. (b) In-control false alarms when each simulated week is resampled from one historical week (keeps between-week noise). (c) Weekly replay of Olist's promise over the whole period, labelled in-sample because its target comes from calibration A. |

### Deviation D1 — the registered CUSUM design could not be run as written (first part-3 run, 2026-10-14T06:05Z)

The first run stopped at its own blocking check: the in-control ARL could not be brought near 52 weeks. Only the
h calibration had been computed and inspected at that point; no simulation or replay result had been looked at.
Cause: with 1,200 orders per week summed into one weekly step, the in-control drift is about −13 per week
(SD ≈ 4.8), so the statistic is almost never positive. Even h = 0 gives an exact in-control ARL of 261.3 weeks
(target 0.90; 321.2 weeks at the Olist-matched target). A negative h has no meaning.

**This is a deviation from the registered design, not a reading of it.** h = 0 was used because it is the
attainable value closest to the registered ARL. At h = 0 the CUSUM never carries evidence from one week to the
next (a positive week alarms and resets; a non-positive week floors at zero), so the rule that was actually run is
a **single-week log-likelihood-ratio threshold**: alarm when a week has ≥ 149 misses out of 1,200 (miss rate above
≈ 12.36%). Its in-control burden is not comparable with the threshold rule's (exact ARL ≈ 2.05 × 10¹⁵ weeks under
the same binomial null). Consequences:

- The v0.6.0 statement that "the CUSUM is better than the threshold rule" is **withdrawn**. The two rules carry very
  different false-alarm budgets, so an earlier alarm cannot be credited to the method.
- The v0.6.0 text "or after smaller excesses accumulate" was wrong and is withdrawn.
- The blocking check was changed from "ARL within 10% of 52" to "h is the attainable h ≥ 0 closest to 52 weeks"
  (v0.6.0); v0.6.1 adds the exact ARLs of both rules and labels the simulated value as a restricted mean.
- A comparison of methods at a common, attainable false-alarm budget would be a **new exploratory experiment**,
  registered separately before it is run. It has not been run.

## Implementation fixes after results had been seen (v0.6.1, 2026-10-14)

None of these changes a registered rule; each brings the code in line with the registered text or reports a
quantity correctly. Results were regenerated; effects are listed.

| # | Fix | Effect |
|---|---|---|
| I1 | B0 quantile: `method="higher"` → `"inverted_cdf"` (the ceil(n·q)-th smallest value), as the registered "smallest whole day covering the target share" requires | MA at 0.95: 45 → 44 days; PE at the matched target: 35 → 34 days. 90% B0 unchanged; no verdict changes |
| I2 | Week finality: Monday + 7 + max promise + 1 → last purchase day (Sunday) + max promise + 1 | every `final_at` and calendar delay 1 day earlier (e.g. week of 2018-05-14: final 2018-06-25) |
| I3 | Simulated ARL reported as a restricted mean (cap 1,000 weeks; censored share shown), plus exact geometric ARL for h = 0 and exact threshold-rule ARL | numbers relabelled, not changed |
| I4 | `to_promise` refuses non-finite input; 1-day / 1-point rule edges use a 1e-9 tolerance | no current result is at either edge |
| I6 (v0.6.3) | Output label for the registered `versus_olist` rule: 'tighter at similar reliability' → `shorter_with_coverage_loss_within_tolerance`. The registered config text is left as written | label only; the rule and every result are unchanged |
| I5 | A stage-7 test retired the real `outputs/stage7_monitoring_report.md` (it was missing from the v0.6.0 ZIP) | test now writes only to a temporary folder |
