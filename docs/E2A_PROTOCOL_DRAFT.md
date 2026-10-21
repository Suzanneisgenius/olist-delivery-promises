# E2a protocol — DRAFT (not registered, not run)

Machine-readable settings: `config/e2a_sim_draft.yaml`. E1 stays sealed; E2a uses synthetic data only and does not
reuse the Olist evaluation period as a test.

## Questions

| | Question | Work | Judged by |
|---|---|---|---|
| Q1 | How should a continuous calibrated bound become a whole-day promise? | Derive the round-down rule; compare round up, round down, subtract one day; ties, whole-number boundaries, floating-point tolerance | The derivation holds; boundary tests pass; assumptions stated. Not by how good the numbers look |
| Q2 | How do rounding and distribution change separately affect coverage? | Paired simulation: same predictor and draws, vary the rule and the calibration–evaluation relation | The mechanisms are separated; mean, spread across replications and Monte Carlo s.e. reported |
| Q3 | How sensitive are the Olist conclusions to the sample window? | Already done post hoc (`docs/E1_POSTHOC_METHODS_REVIEW.md` §4); reported as such | Direction, size and coverage compared; never called a removal of bias |

## Simulation (Q2)

Scenarios: S1 same distribution; S2a/S2b later deliveries 15% faster/slower (scaled before rounding); S3 heavy ties
(coarse support, predictor in half-day steps); S4 only delivered-by-freeze calibration labels. Predictors: continuous
median and its whole-day rounding. Rules: round up, round down, subtract one day, plus the continuous bound as
reference. Paired within each replication. n_cal 2,000, n_eval 5,000, 2,000 replications, seed 20261101.

Expectations written before the run (not success criteria; a mismatch is reported, not tuned away): round down meets
k/n on calibration in every replication (with the one-day minimum: at least, not exactly, the event of U); under S1
its mean evaluation coverage is ≥ q up to Monte Carlo error; subtract-one is not coverage-preserving in general and
is expected to fall below k/n on calibration where the one-day minimum rarely binds (the k-th order always sits on a
whole-number bound), while it can still cover where the minimum binds; ties can over-cover under every rule; under S2 and S4 no rule restores the guarantee. The simulation
reports how often the one-day minimum binds in each cell.

## Before anything runs

1. The author works through the Q1 derivation and the counterexample personally.
2. The author confirms or edits the YAML; its SHA-256 is logged in `docs/E1_DECISIONS.md`.
3. Code is written and tested on other seeds; the registered seed runs once.

Out of scope: online / adaptive recalibration (Olist labels arrive late and the first delivered orders are not a
random subset), new forecasting models, a new Olist cohort.
