# Explainer card — Stage 7: promised delivery dates (length and re-check)

**One sentence.** I asked whether the promised delivery date could be shorter and still kept as often, froze
four promise rules at 2018-04-01, scored them on later orders, and then tested two alarm rules that say when a
frozen rule should be reviewed.

## Three things to be able to explain
- **Coverage vs tightness.** A promise can always be kept by making it longer. So every result has two numbers:
  share of orders delivered on or before the promise, and mean promised days. The registered rule kept a
  complex model only if it was ≥ 1 day shorter with ≤ 1 point lower coverage.
- **Conformal shift.** Add to the regression's prediction the ⌈(n+1)·0.9⌉-th smallest calibration error. This
  guarantees ≥ 90% marginal coverage *if* calibration and test scores are exchangeable; with time change and
  selection in this design, that premise cannot be relied on. In practice the calibration windows had higher
  late rates (7–9% vs 4%) and 0.90 became ~96%, with longer promises; the causes were not separated.
- **CUSUM, and why mine is not one.** A CUSUM adds up evidence that the miss rate is 15% rather than 10%, week
  after week, floored at 0. With 1,200 orders a week the in-control drift is so negative that the registered
  52-week false-alarm interval was unreachable; I used h = 0 (deviation D1). At h = 0 nothing carries over between
  weeks, so the rule I ran is a single-week likelihood-ratio threshold (alarm at ≥ 149 misses of 1,200).

## Results
| | Result |
|---|---|
| Complex model worth it? | No. Regression + shift was 2.6 days *longer* than the per-state rule; the plain regression was shorter but 4.4 pts less reliable. |
| vs the current promise | The per-state rule was 3.0 days shorter at 0.8 pts lower coverage (Olist-matched target): within my 1-day / 1-point tolerance, not a proof of equal reliability. |
| Which alarm? | Not decided. The single-week rule caught a 20% slowdown in 93% of runs (median 5 weeks) and the threshold rule never did, but their exact in-control ARLs are 261 weeks vs ~2 × 10¹⁵ weeks (independent binomial weeks), so this is not a fair comparison. |
| Real history | The single-week rule fires once in the evaluation period: purchases in the week of 2018-05-14 (85.1% covered, final on 25 June). |

## Limits (say these before you're asked)
- Exploratory: I had seen the data in stages 1–6 before writing the design.
- One evaluation period (purchases Apr–Jul 2018); late weeks are thinned by how the population was selected.
- Why calibration over-covered is not separated: timing, order mix and label observability all changed together.
- Coverage is overall, not per state: in BA the state rule kept 88.2% and Olist's promise 84.6% (target 90%).
- Real weeks are ~20× noisier than the simulation assumes; resampling real weeks gives ~3.6 alarms a year.
- No customer outcome: whether shorter promises sell more or annoy more is not observed.
