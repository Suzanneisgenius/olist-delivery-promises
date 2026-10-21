# E1 post-hoc methodological review (fourth review, 2026-10-21; corrected after the fifth review)

Status: POST HOC. Written after the E1 scoring run. The sealed archive (`olist-e1-snapshot-v2.zip`), `FREEZE.json`
(SHA-256 `3b62af1a…328dd`), the registered H1–H3 results and every file under `src/` are unchanged. Nothing here
fits a model, selects a policy or changes a registered verdict.

Code and outputs: `scripts/e1_rounding_rules.py`, `scripts/e1_posthoc_methods.py` → `outputs/e1/posthoc_m4/`
(with `MANIFEST.sha256`); tests `tests/test_posthoc_rounding.py` (45: identity, counterexamples, one-day minimum,
boundary and tolerance cases, and refusal of non-finite shifts, empty / 2-d input, overflow and non-integer labels;
red/green logs in `outputs/e1/redgreen_rounding/`). Earlier round: `scripts/e1_posthoc_review3.py`
→ `outputs/e1/posthoc_r3/`.

## 1. What the registered results can and cannot say

| Topic | Wording now used |
|---|---|
| HGB lower loss, longer dates | Two frozen policies at different realised coverage on E (D\* 97.10%, C\* 96.18%); not evidence about which model is better at equal reliability |
| "Same calibration, so fair" | Matched training orders, label timing, feature rule and calibration procedure; rounding up treats continuous and whole-day predictors differently |
| E window | Stated in the sample definition (main text §3): Olist estimated week ≤ 2018-07-23 |
| B0 not replaced | The registered policies did not meet the pre-set replacement standard; not "the models have no decision value" |
| H2 | Machine record kept ("not supported"); text: V selected no new linear setting, so no comparison between different linear models was formed |
| Title | "Integer-valued delivery promises: calibration, coverage and temporal shift" (no causal mechanism in the title) |

## 2. Two layers of evidence in the main figure

Filled squares: policies calibrated on C only, frozen, scored once on E. Dashed lines: diagnostic curves whose shift
uses E's own outcomes; descriptive only, not deployable, not used to choose a model. Matched comparisons report the
coverage actually reached (coverage moves in steps); no interpolation (`matched_coverage_E.csv`).

## 3. Rounding a continuous bound to whole days

R_i = Y_i − f̂(X_i), k = ⌈(n+1)q⌉, s = R_(k), U = f̂ + s.

- Round up (registered): Y ≤ U ⇒ Y ≤ ⌈U⌉. Valid and conservative; adds slack when U is not a whole number.
- Round down: Y integer ⇒ (Y ≤ U ⇔ Y ≤ ⌊U⌋), so the UNTRUNCATED ⌊U⌋ has exactly the coverage event of U.
  The one-day minimum max{1, ·} can only enlarge it, so the event is then at least, not exactly, that of U
  (Y ≡ 1, f̂ = 0, …, 99, q = 0.9: U covers 91%, max{1, ⌊U⌋} covers 100%).
- Subtract one day, max{1, ⌈U − 1⌉}: equals ⌊U⌋ unless U is a whole number, then one day less (before the
  minimum). Not coverage-preserving in general: Y ≡ 10, f̂ ≡ 0.5 ⇒ s = 9.5, U = 10; round down covers 100%,
  subtract-one 0%. Without the minimum its calibration event is R_i < R_(k) (fewer than k orders); with the
  minimum it need not under-cover: Y ≡ 1, f̂ ≡ 0.5 ⇒ U = 1, max{1, ⌈0⌉} = 1 covers 100%.
- On the saved E1 data every bound is ≥ 12.5 days on C and E, so the minimum never binds and no table changes.
- Floating point: compare with U ± 1e-9 in the direction that keeps the event.

On E1 (`rounding_rules.csv`): rounding down gives C coverage 90.01% (= share with Y ≤ U ≥ k/n = 90.009%) for every
continuous policy and shortens each continuous promise by exactly 1 day on E; B1c is unchanged. Subtract-one gives
90.00% on C for continuous policies and 89.08% for B1c. The third-review table used subtract-one for continuous
predictors only; its E numbers equal round-down to two decimals on these data (one E order, for C*, has a bound within 1e-6 of a whole number), but the rule is replaced.

Two different quantities: mean (⌈U⌉ − U) on E ≈ 0.50 day (C\* 0.497, D\* 0.503) is the arithmetic part of the
registered promise; ⌈U⌉ − ⌊U⌋ = 1 day is the counterfactual change from switching rule.

## 4. Sample selection and stability

Wording: coverage is higher in the later, more heavily selected months; this is consistent with a contribution from
the window restriction but does not separate it from temporal or order-mix changes. The 0.60–0.91-day HGB–linear
gap holds at the four reported targets, not at every coverage level.


- `e_sample_flow.csv`: of 32,803 purchases from 2018-04-01, the estimated-week condition keeps 20,650; July 1,117 of
  6,292; August onward none. Delivered: 20,296; single seller: 19,950 = E.
- `e_window_comparison.csv`: full E, April–May, June–July side by side (same cohort rule; a sensitivity check, not a
  bias correction). A cohort independent of Olist's estimated date would be a new design.
- Seasonality of C: candidate explanation only.
- `leave_one_week_out.csv`: no registered difference changes sign when any one of the 17 weeks is removed; the
  Olist day difference ranges −1.41 to −0.35. Stability diagnostic, not an interval. The registered intervals stay,
  with their limits (17 clusters, models fixed, no refit or selection uncertainty).

## 5. Next step

`docs/E2A_PROTOCOL_DRAFT.md` + `config/e2a_sim_draft.yaml`: a small methods study (rounding rules; paired simulation
of rounding, temporal shift, ties and selective labels). Drafted, not registered, not run. Online recalibration is out
of scope (delayed, non-random labels).
