# Stage 2 developer UI checks

Executed locally on 2026-10-12 in the Codex in-app browser, using the regenerated HTML.
These are developer observations, not business-owner UAT sign-off.

| Case | Expected | Observed |
|---|---|---|
| Default latest comparison | 2018-07-16 → 2018-07-23; -1.80 pp | Matches; visible contribution bars and counts |
| Largest decline button | 2018-03-12 → 2018-03-19; -9.58 pp | Matches; 2,189 → 2,081 eligible orders |
| Select first comparable week | 2017-02-27 → 2017-03-06; -0.40 pp | Matches; 341 → 428 eligible orders |
| Latest pair reset | Restore latest comparison | Matches |
| Seller sample threshold | 30 → 100 → 30 changes only seller queue | 547 → 181 → 547 qualifying sellers |
| Full state details | Include all states, even below ranking threshold | 23 state rows in latest comparison |
| Download selected pair | Export same displayed pair | Browser downloaded 23-row CSV; compared field-for-field with computed pair |
| Whole-window scope | Global trend, stages and totals unaffected by pair selector | 92.92%, 84,129 eligible; stage sample 77,198 / 5,934 retained |
| Stage chart | Median hours visible, common zero-based scale | Handling 44.2 / 72.5; transit 170.3 / 657.0; P90 table visible |
| Normal layout | Visible marks, legends and labels | Observed at default browser width; no clipping in inspected charts |
| Narrow layout | Wrapping controls/cards; contained horizontal chart/table scroll | Observed at effective width 284 px; no document-wide overflow |
| Runtime errors | No uncaught errors | Browser error log empty in checked paths |

CSV comparison confirms exact values before rounding. Dates, counts and rates in the
browser were checked against the generated aggregate outputs. Screenshots were inspected
for the opening view, trend, stage chart and narrow layout. Not every week/pointer state
was individually tested; shared calculation paths are covered by SQL checks and tests.
`reviewer_ok` in the Stage 1 manual sample has not been filled by this run.
