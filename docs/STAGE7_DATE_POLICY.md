# Stage 7 — How long should the promised delivery date be, and when should it be re-checked?

Exploratory extension (v0.6.3). The data had already been inspected in stages 1–6, so this is a **historical
method experiment**, not a confirmatory test and not a pilot. Design registered in `config/date_policy.yaml`;
every change and every reading of the registered text is in `docs/DATE_POLICY_DECISIONS.md`.

Run: `python -m olist_analytics.run_stage7` (parts 1–2), then `python -m olist_analytics.run_stage7_monitor`
(part 3). Both are steps in `run_all`. Reports: `outputs/stage7_date_policy_report.md`, `outputs/stage7_monitoring_report.md`.

## Question and definitions

- **Required days** = delivered calendar day − purchase calendar day. **Promise** = whole days. An order is
  **covered** if required ≤ promise. This is the project's on-time rule, checked in the run: required > Olist's
  promise exactly for the stage-3 late orders.
- **Coverage** = share of orders covered. **Tightness** = mean promised days.
- Population: single-seller orders with a final on-time/late outcome (stage-3 population). Canceled and
  unconfirmed orders are not covered.

## Design (frozen 2018-04-01)

| Rows | Purchases | Use |
|---|---|---|
| fit | before 2017-10-01, delivered before the freeze | fit B0 (with cal_A) and the regression |
| calibration A | 2017-10-01 → 2017-12-31 | conformal shift (outcomes complete) |
| calibration B | 2018-01-01 → 2018-03-31, delivered before the freeze | conformal shift (most recent; 81% of the window observable) |
| evaluation | 2018-04-01 → 2018-07-19 (last purchase in the population); latest delivery record in this sample 2018-10-17 (not an administrative follow-up cut-off) | one out-of-time evaluation of the frozen policies by design; the data had been analysed and re-run many times, so this is not a blind test |

| Policy | Rule |
|---|---|
| B0 | per customer state, the smallest whole day d covering the target share of fit + calibration-A orders, i.e. the ⌈n·q⌉-th smallest value (overall value if < 300 orders) |
| Q1 | linear quantile regression on log1p(required days), 13 purchase-time inputs (Olist's own estimate excluded) |
| Q2A / Q2B | Q1 + a one-sided split-conformal shift from calibration A / B |
| Olist | the existing estimated delivery date |

Registered rule for "is the complex model worth it": keep it only if mean promised days are ≥ 1 day shorter than B0
**and** coverage drops by ≤ 1 point.

## Results — parts 1 and 2

Evaluation: 19,950 orders (late rate 4.3%, lower than the 8.7% and 7.0% in the calibration windows).

| Target 0.90 | Coverage | Mean promised days |
|---|---|---|
| B0 state rule | 93.9% | 20.3 |
| Q1 regression | 89.5% | 16.9 |
| Q2A regression + shift (A) | 96.4% | 22.9 |
| Q2B regression + shift (B) | 96.3% | 22.6 |
| Olist promise | 95.7% | 24.4 |

1. **The complex model is not kept.** Q2A is 2.6 days *longer* than B0; Q1 is 3.4 days shorter but 4.4 points less
   reliable and falls to 84.0% in May 2018. Same verdict at targets 0.95 and Olist-matched (0.9126).
2. **The state rule is 3.0 days shorter than the current promise, with 0.8 points lower coverage** (Olist-matched
   target: 94.9% vs 95.7%; 21.4 vs 24.4 days). This meets the registered point-estimate tolerance (≥ 1 day shorter,
   ≤ 1 point lower). It is **not** a demonstration of equal reliability and not a non-inferiority test: the registered
   rule asked for no interval.
3. **Calibration over-covered.** Shifts of ~6.0 (A) and ~5.8 (B) days made the 0.90 target cover ~96%. Calibration A
   was not better than B (mean absolute monthly gap 6.9 vs 6.8 pts). Timing, order mix, seller-history snapshots and
   label observability all differ between the windows and the evaluation period (which is also shaped by the
   estimated-week population window); **this experiment does not separate their contributions.** Split conformal's
   marginal guarantee requires the calibration and test scores to be exchangeable (Angelopoulos & Bates, 2021). The
   time change and selection in this design mean that premise cannot be relied on here; over-coverage alone does not
   prove it is violated.
4. **Descriptive trade-off curves** (computed on evaluation labels after the fact; not used for decisions): at equal
   coverage, interpolated, Q2 is about 0.3–0.9 days shorter than B0, and B0 is about 1.8–2.6 days shorter than
   shifting every Olist promise by the same amount. This hints that the regression might be worth re-calibrating;
   it is a difference in efficiency on these labels, not a ranking metric, and it would need a new frozen evaluation.

## Results — part 3 (monitoring B0 at target 0.90)

Rules (registered): threshold — weekly coverage < 85% for 2 consecutive weeks (≥ 200 orders each);
Bernoulli CUSUM — p0 = 0.10, p1 = 0.15, weekly sums, h for an in-control ARL of ~52 weeks. Alarms trigger review only.

**Deviation D1: the registered CUSUM could not be run as designed.** With 1,200 orders per week the weekly in-control
drift is ≈ −13 (SD ≈ 4.8), so even h = 0 has an exact in-control ARL of 261 weeks; 52 weeks is unreachable. h = 0
was used. At h = 0 the statistic never carries over from one week to the next, so **the rule actually run is a
single-week log-likelihood-ratio threshold**: alarm when a week has ≥ 149 misses out of 1,200 (miss rate above
≈ 12.36%). It is called the *single-week LLR rule* below.

The two rules carry very different false-alarm burdens. Assumption for both rows: independent binomial weeks of
1,200 orders at the target miss rate (p0 = 0.10). The crossing probability q is for one week; for the threshold rule
it is not the rule's alarm probability, because an alarm needs two consecutive crossings.

| Rule | One-week crossing probability q | Full alarm condition | Exact ARL (after reset) |
|---|---:|---|---:|
| single-week LLR (CUSUM at h = 0) | 0.003827 | this week ≥ 149 misses of 1,200 | 1/q = 261.300 weeks |
| threshold | 2.2093 × 10⁻⁸ | two consecutive weeks each ≥ 181 misses of 1,200 | (1+q)/q² ≈ 2.0487 × 10¹⁵ weeks |

Simulation, order bootstrap of evaluation orders (registered; 500 × 30 weeks × 1,200 orders). Calendar delay = days
from the change start to the date the alarm week is final (its Sunday + longest promise + 1 day):

| Scenario | Coverage after change | Single-week LLR: detected / median delay | Threshold: detected / median delay |
|---|---|---|---|
| none | 94.0% (no change) | 0 alarms in 30 weeks × 500 | 0 alarms |
| sudden × 1.2 from week 9 | 88.7% | 93% / 5 weeks (≈ 77 days) | 0% |
| gradual +2%/week from week 5 | 86.4% (78% by week 30) | 100% / 10 weeks (≈ 112 days) | 100% / 17 weeks (≈ 161 days) |
| transient × 1.3, weeks 9–10 | 85.5% in week 9 | 100% / 0 weeks (≈ 42 days) | 10% |

What these numbers do and do not show:
- **They do not show that one method is better.** The single-week LLR rule alarms earlier, but its long-run
  in-control alarm frequency (1/ARL) is about 8 × 10¹² times the threshold rule's (ratio of the two ARLs, not of
  the two crossing probabilities). Zero false alarms in a finite simulation does not mean equal false-alarm rates.
  A method comparison needs a common, attainable false-alarm budget — a new experiment, registered separately.
- **The policy's cushion hides small shifts.** B0 ran at 94% against a 90% target, so a 20% slowdown only brought
  coverage to 88.7%. Both rules compare with the target, not with the level the policy actually achieved.
- **Calendar delay is dominated by when a week becomes final.** A week is final only after its longest promise
  (35 days for B0) + 1 day, so even a same-week alarm comes ~6 weeks after the week started.
- That the 52-week ARL is unreachable with weekly batches of this size is itself a design finding.

**Exploratory (M7, no decision uses these):**
- **Real weeks are far noisier than the bootstrap.** Week-to-week variance of coverage is 22× the binomial value
  in the evaluation period (34× for Olist's promise over the whole period). Part of the evaluation figure comes
  from June–July weeks thinned by the population window (see limits), so treat the size as rough.
- Resampling whole historical weeks instead of orders gives 3.6 single-week LLR alarms per year with no injected
  change, vs 0 under the order bootstrap: the registered simulation understates alarms. Most come from one real
  week (below), so calling them "false" is debatable.
- **Historical replay.** Both rules were applied week by week on the evaluation period. The single-week LLR rule
  fires once for B0: purchases in the week of 2018-05-14 (coverage 85.1%; final on 2018-06-25). The threshold rule
  does not fire: 85.1% is just above 85%, and the next week recovered. One possible explanation (outside knowledge,
  not tested here) is the nationwide truck drivers' strike in Brazil in late May 2018. Over the whole period, Olist's
  own promise would have triggered the single-week rule in late November 2017 and in February–March 2018 (in-sample
  illustration).
- Replay is computed per purchase week and then labelled with `final_at`; weeks are not re-ordered by when their
  information arrives (Olist's whole-period `final_at` goes backwards 22 times). This cannot change the memoryless
  h = 0 alarms, but any rule with state would need an explicit arrival/buffer rule.

## Limits

- Exploratory: the data were seen before the design; thresholds and windows were chosen by me, not by a business
  owner. The config hash shows the config did not change after registration; it cannot show by itself when the
  design was written.
- Population = single-seller orders with a final outcome, selected by estimated delivery week. Late purchase
  weeks (June 2018 on) are thinned: orders with long promises or still undelivered at the data end are missing,
  so their coverage is biased upward and order counts fall (77 orders in the last week).
- Coverage is marginal (over all orders), not per state or per order. B0's lowest reported state is BA (88.2% of 638
  orders, below the 90% target; Olist's promise is lower still there, 84.6%).
- No customer-behaviour outcome: a shorter promise may raise conversion or lower satisfaction; neither is observed.
- The monitoring simulation draws orders independently; real weeks share shocks (over-dispersion above).
- The median-required-days signal uses final delivery dates, which are not all known when a week's coverage is
  final. There is no reliable record of when events entered the system, so real-time timeliness is not validated.
- One evaluation period (purchases April–July 2018); a full seasonal cycle is not covered.
- The quantile regression uses scikit-learn's `QuantileRegressor` (HiGHS solver). My work is the features, time
  splits, calibration, evaluation and monitoring design, not the optimiser.

## Next steps worth trying (not run; each would be registered first)

1. **Compare alarm rules at an equal false-alarm budget.** Under an explicitly stated resampling null, estimate
   thresholds that reach a similar false-alarm budget, report the Monte Carlo error and the censored share, then
   compare detection delay. A simulated budget is an estimate, not an exact value.
2. **Monitor by due date, not purchase week.** Count an order once its promise has passed; that removes most of
   the 35-day finality lag.
3. **Over-dispersion-aware limits** (e.g. beta-binomial or week-resampled calibration) instead of the binomial.
4. **Recent-window calibration** for Q2 (e.g. the last 8 complete weeks), scored on a new frozen period. It may or
   may not fix the over-coverage.
5. **State-level coverage floor** (e.g. no state with ≥ 300 orders more than 3 points below target) as a second constraint.
