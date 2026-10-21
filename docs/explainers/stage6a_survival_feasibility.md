# Explainer card — Stage 6a: is a survival model feasible here?

**One sentence.** Before fitting any survival model, I checked which missing delivery dates are real
censoring and which are something else, because treating them all as "still in transit" would bias the model.

## Key idea
- Event = delivery. S(t) = P(not delivered yet at time t after purchase).
- Late = not delivered by the end of the promised day ⇒ **P(late) = S(deadline)**, not 1 − S.

## Two views of every order
- **Final file**: what the last record says. Describes the data, but is not what was known earlier.
- **Reconstructed at a cut c** (exclusive): rebuilt from event dates, assuming timely recording — not a real
  historical snapshot. Unresolved ≠ in transit: it mixes in-transit,
  later-cancelled and never-recorded orders. Guards: entry < c, event < c, durations > 0.
- The observation end is a date I had to make explicit: 2018-09-04 00:00 (primary), midnight 09-03 as sensitivity.

## Kinds of "no delivery time"
| Kind | Treat as censored? |
|---|---|
| Unresolved at a cut we choose | yes, as of that cut (if censoring is independent given covariates) |
| Recent U (≤ 31 days past promise) | only a **candidate**: no last-tracking time in the file |
| Stale U (median 251 days past promise) | no: missing outcome, mechanism unverifiable |
| Cancellation (X), no timestamp | no: competing terminal event |
| Canceled but with a delivery date (6) | isolated as a record–status conflict |

## The honest catch
At 2018-04-01, 5,434 window orders were unresolved; in the final file 30% of them end as U or X, and nothing at
the cut tells them apart.
- E_A (only orders that end A/L): comparable with the classifier, but selecting them uses the future → a method
  experiment at most.
- E_B (no delivery by the deadline): needs a decision on "no record" vs "no actual delivery", a finite horizon,
  and its own evaluation population; a standard log-normal AFT (S → 0) does not fit a never-delivered share.
I withdrew my first recommendation (fit E_B, evaluate on the A/L cohort): those two did not match.

## Say it in an interview
"Survival analysis is not a free fix for missing labels. I separated what the final file says from what was
known at each cut-off, found that most 'unconfirmed' orders were months overdue and cancellations had no
timestamp, and concluded the estimand has to be chosen before any model — stopping at that finding is a result."

## Don't claim
No survival model has been fitted. Recent U are not "confirmed censored". Stale U are not "proven informative".
