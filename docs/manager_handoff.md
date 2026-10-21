# Manager handoff — Olist delivery performance & late-delivery risk (v0.6.3)

## What it answers
1. **How did on-time delivery change week to week, and where?** Weekly on-time rate among delivered orders with valid dates, split by customer state into performance and mix (Weekly Review page).
2. **Can the data be trusted?** Every order in exactly one outcome bucket, amounts reconciled to the raw files, independent SQL re-counts (Data Quality page).
3. **Can late orders be ranked at checkout?** A time-split, leakage-checked model ranks late orders about 3× better than random on a later period (Model Report page).

4. **Could the promised date be shorter, and when should it be re-checked?** Exploratory stage 7: a per-state rule gave about 3 fewer days at 0.8 points lower coverage than the current promise (within the pre-set tolerance; no interval). Which alarm rule is better is not established: the two rules tested carry very different false-alarm burdens (`docs/STAGE7_DATE_POLICY.md`).

## Headline numbers (from the current run; each page shows its source file)
| Item | Value |
|---|---|
| Window | estimated weeks 2017-02-27 → 2018-07-23 (74 weeks) |
| On-time rate (delivered, valid dates) | 92.92% of 84,129 orders; U 1,563; coverage 98.18% |
| Largest weekly decline | 2018-03-12 → 2018-03-19, −9.58 pts, broad across states |
| Model (logistic, chosen on development data) | test AP 0.123 vs 0.043 late rate; top 10% per week: 13.0% precision, 30.5% of late orders |
| Monthly backtest (stage 5, same models refit at each month start) | AP 0.167 / 0.179 / 0.050 for Apr / May / Jun 2018 vs late share 4.6% / 6.7% / 1.3% (2.7–3.9× the constant reference): a ranking signal each month; stability not established; not a new test |
| Promised dates (stage 7, purchases 2018-04-01 → 07-19, exploratory) | per-state rule 94.9% covered, 21.4 days vs Olist 95.7%, 24.4 days; regression + calibration 96.4%, 22.9 days at a 90% target (over-covered) |

## How to use it
- Read on-time rates with U and coverage beside them; never fold U into on-time or late.
- Use the model's **ranking**, not its probabilities (they run high under drift).
- Treat state contributions and feature importance as description, not cause.

## Known limitations
- Late cohorts near the end of the file may be censored; the window stops early for that reason (31/45/60-day sensitivity on the Data Quality page).
- `estimated_days` assumes the stored estimate is the one shown at checkout; without it AP falls to about 0.068.
- Model population = single-seller orders with a final on-time/late outcome; no claim about canceled, unconfirmed or multi-seller orders.
- No carrier identifiers in Olist; sellers are not carriers; estimated dates are not SLAs.
- The test period was evaluated before and after a protocol fix; it is not a fresh confirmatory test.
- Stage 7 is exploratory (data seen before the design); one evaluation period; no customer-behaviour outcome.
- Offline analysis on a public 2016–2018 snapshot; no business outcome was measured.

## Open items
- Owner review of the 20-order sample (UAT-13) and acceptance of conclusions/limits (UAT-14).
- Survival model: feasibility review rev. 2 (`docs/STAGE6A_SURVIVAL_FEASIBILITY.md`); owner chooses O1 (stop) / O2 (E_A method experiment) / O3 (E_B redesign) before any model.
- Optional: delay ↔ review-score association (3b); probability recalibration on a separate, pre-scoring calibration set; multi-seller orders.

## Where things are
Run steps: `docs/refresh_checklist.md`; reproducibility record: `docs/REPRODUCIBILITY.md`. Acceptance: `outputs/stage4/UAT.md` (sign-off in `uat/owner_signoff.csv`). Definitions: `docs/metric_dictionary.md`. Model: `docs/model_card.md`.
