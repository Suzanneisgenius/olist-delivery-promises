# Explainer card — Stage 5: monthly rolling-origin backtest

**One sentence.** I re-fit the two stage-3 models at three monthly cut-offs, each time using only labels and
seller history that existed at that date, and checked whether each month still shows a ranking signal.

## How a fold works (cut-off T)
- **Fit**: orders purchased before T **and delivered before T** (the label exists only after delivery).
- **Evaluate**: orders purchased in [T, T + 1 month).
- **Seller history**: fit rows use month-start snapshots; evaluation rows use one snapshot frozen at T.
- **No tuning**: the stage-3 hyperparameters are reused, so no choice is made from these months.
- **Self-check**: the 2018-04-01 fold has the same data as stage 3 and reproduces its April scores
  (max difference ~1e-16).

## Results (logistic; baseline = the month's late share)
| Cut-off | Late share | AP | AP / baseline | Top-10% precision | Top-10% recall | Mean predicted |
|---|---:|---:|---:|---:|---:|---:|
| 2018-04-01 | 4.6% | 0.167 | ×3.6 | 17.8% | 38.6% | 7.7% |
| 2018-05-01 | 6.7% | 0.179 | ×2.7 | 20.8% | 31.2% | 11.0% |
| 2018-06-01 | 1.3% | 0.050 | ×3.9 | 4.3% | 34.3% | 5.7% |

ROC AUC (logistic): 0.790 → 0.747 → 0.723. Logistic had higher AP than GBM in every fold. The months contain 6/5/5
purchase-week segments (partial weeks included), so no interval is given and the size of the gap is not established.

## What it shows
- In each of the three selected monthly cohorts the model keeps a ranking signal above the constant reference.
- Over-prediction persists in every month: probabilities are not risk levels.
- **Temporal stability is not established**: three points, different cohorts, no intervals. AP/baseline is not a
  drift-adjusted stability measure, and the AUC drop is not shown to be significant either.

## Limits (say these before you're asked)
- **Not a new test**: every month is inside the already-inspected stage-3 test period.
- The June fold is the least comparable: 435 of 6,167 June purchases fall outside the approved window
  (their promised week is after 2018-07-23), and only final A/L orders are scored.
- Training drops orders still in transit at T, and those are much more often late (39% at 2018-04-01).

## Likely question
*"Why not sklearn's TimeSeriesSplit?"* — It splits by row position. Here a training row is valid only if
its **delivery** happened before the cut-off, and seller features must be frozen at the cut-off; the split
has to be built from dates, not positions.
