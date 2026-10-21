# Metric Dictionary (approved 2026-10-12, with conditions)

Olist-specific metrics for this project. They are **not** the KPI list from any internship.
Cohort: `estimated_week` = Monday of `order_estimated_delivery_date`. Not called an SLA.
Default window: estimated weeks 2017-02-27 → 2018-07-23 (74 weeks), a retrospective comparison window
chosen by the rule in `outputs/stage1_quality_report.md` §9; keep the censoring note and sensitivity table with it.

## Outcome buckets (order grain, mutually exclusive)
| Bucket | Rule |
|---|---|
| A | status `delivered`, delivery timestamp present and ≥ purchase, delivery **date** ≤ estimated **date** |
| L | same as A but delivery date > estimated date |
| U | outcome unconfirmed: in-progress status (shipped, invoiced, processing, created, approved), delivered without a date, or delivery before purchase |
| X | `canceled` or `unavailable` (no assumption about when they were canceled) |
| NO_VALID_ESTIMATE | estimated date missing or earlier than purchase (0 orders in this file); never assigned to a week, counted separately so weekly totals + unassigned = all orders |

U is never treated as on time, and never silently treated as late.

## KPIs
| ID | Name | Grain | Numerator / value | Denominator / sample | Shown with |
|---|---|---|---|---|---|
| OTD_DELIVERED | On-time rate among delivered orders with valid dates (name must keep this wording) | order | A | A + L | U count, outcome coverage, X count, eligible denominator, week range |
| OUTCOME_COVERAGE | Outcome coverage (guardrail) | order | A + L | A + L + U | — |
| CYCLE_HOURS | Purchase → delivery hours, median and P90 | order | per-order `total_hours` | A + L orders | sample size |
| HANDLING_HOURS | Payment approved → carrier handoff hours, median and P90 | order | `handling_hours` | `is_stage_eligible` | sample size |
| TRANSIT_HOURS | Carrier handoff → delivery hours, median and P90 | order | `transit_hours` | `is_stage_eligible` | sample size |
| ELIGIBLE_ORDERS | Orders in the OTD base | order | count(A + L) | — | X and U counts |

Auxiliary only: confirmed on-time share A / (A + L + U). Never mixed with OTD_DELIVERED.

## Stage timing (diagnosis, not responsibility)
`total = approval + handling + transit` holds per order for stage-eligible orders (checked, max gap 0 h).
Medians of stages are not added to get a total median. No "share of delay caused by seller / carrier" is reported:
Olist has no per-stage standard to measure against.

Stage-2 diagnostic: share of orders handed to the carrier after the seller's `shipping_limit_date`
(earliest across the order's items). It is Olist's seller hand-off deadline; transit has no comparable
standard, so no stage "responsibility share" is reported.

## Eligibility flags
| Flag | Meaning |
|---|---|
| `is_otd_eligible` | bucket A or L |
| `is_stage_eligible` | valid delivery, approval and carrier timestamps present, no timestamp-order anomaly |
| `is_model_eligible_prelim` | OTD-eligible and single seller (feature-availability rules come in stage 3) |
| `is_review_eligible` | has a review answered on/after delivery (primary = first such review) |

## State decomposition (approved spec for stage 2)
For one pair of comparison weeks, P0 and P1 are overall OTD; c = (P0 + P1) / 2 (same for every state).
Shares w and rates p use the same OTD-eligible denominator (A + L); state `UNKNOWN` is a normal group.

```text
states in both weeks:
  performance_s = ((w_s,0 + w_s,1) / 2) * (p_s,1 - p_s,0)
  mix_s         = (((p_s,0 + p_s,1) / 2) - c) * (w_s,1 - w_s,0)
entering / exiting states (no rate in the missing week; never filled with 0):
  entry_s =  w_s,1 * (p_s,1 - c)
  exit_s  = -w_s,0 * (p_s,0 - c)
sum(performance + mix + entry + exit) = P1 - P0      (asserted)
```
With an unchanged state set, centring changes how the mix term is attributed to each state, not its total; with entering or exiting states only the overall identity is fixed. Mixing centred mix with
uncentred entry/exit (w1*p1, -w0*p0) breaks the identity. Results are in percentage points and describe
where the change sits, not what caused it. A state with zero eligible orders in both weeks is not comparable.

## Stage 2 inspection rules

- Figure 04A ranks states only when both weeks have at least 30 eligible orders.
  Small, entering and exiting states remain in exact totals and the full export.
- Seller queue: one seller per order, full approved window, A/(A+L); U, X and
  stage-valid n are separate. Default minimum A+L is 30, selectable 100 or 300.
  Multi-seller orders remain in main KPIs and state decomposition, but not this queue.
- Seller Wilson 95% interval uses z=1.95996398454. It is a binomial descriptive
  interval, without adjustment for within-seller dependence, confounding or censoring.
- Earliest-item-deadline check compares order-level handoff with minimum
  `shipping_limit_date` across items. It is a proxy, not individual seller compliance.
- Stage distribution sample is `is_stage_eligible AND is_otd_eligible`; median,
  P90 and mean use actual per-order hours, not subgroup medians.
