# Model Card — Purchase-time Late-Delivery Risk (v0.3.1, offline)

| Item | Value |
|---|---|
| Task | Rank single-seller orders at checkout by risk of delivery after the estimated day |
| Data | Public Olist snapshot (CC BY-NC-SA 4.0), source hashes in `outputs/qa/source_manifest.csv` |
| Population | Approved-window orders with final outcome A/L and one seller (`outputs/stage3/population_steps.csv`) |
| Split | Purchase time: train < 2018-01-01 ≤ dev < 2018-04-01 ≤ test (2018-04-01 → 2018-07-19) |
| Label rule | Training labels precede the fit cut-off; model-selection development labels also precede 2018-04-01 (`label_availability.csv`) |
| Seller history | Snapshot rule: labels delivered before T; training rows T = month start, evaluation rows T = block start (frozen) |
| Models | Constant baseline; logistic regression (headline, chosen on dev); histogram gradient boosting (comparison) |
| Primary metric | Average precision (AP); also ROC AUC, Brier, top-10% per purchase week precision/recall |
| Result (test) | See `outputs/stage3_model_report.md` §5; all numbers come from that run |

## Intended use
Portfolio demonstration of time-split ranking with explicit information-availability rules.
Not deployed. No operational outcome measured. v0.3.1 corrects unavailable development
labels in v0.3.0; the test set was already inspected and this is a revised benchmark.

## Not for
- Probability estimates as-is (over-predict under drift; see report §5 calibration).
- Orders that are canceled, never confirmed, or multi-seller (not in the population).
- Any causal claim about why orders are late. Importance is predictive only.

## Known limits
- `estimated_days` assumes the stored estimate equals the one shown at checkout; AP drops sharply without it (report §6).
- Training excludes rows whose label was unknown at the cut-off; those rows are much more often late.
- Strong prevalence drift: train 5.7% → dev 13.0% → test 4.3%.
- Distance = zip-prefix straight-line proxy.
- Other stored checkout/profile fields also lack historical version records.
- Development late rate is 13.0% with eventual labels, but 6.97% among labels actually
  available for model choice. Pending labels are disproportionately delayed.
- Historical handling medians use stage-valid records only. Known A/L labels use their own eligibility.

## Reproduce
`PYTHONPATH=src python -m olist_analytics.run_stage1 && … run_stage2 && … run_stage3`
Tested locally with Python 3.12.14, pandas 2.3.3, NumPy 2.5.1, DuckDB 1.5.5,
PyYAML 6.0.3, scikit-learn 1.9.0. Run `python scripts/verify_stage3.py` after modelling
for an independent source/score check; its results are saved in `independent_verification.json`.
