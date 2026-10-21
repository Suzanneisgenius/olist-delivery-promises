# External references

Checked on 2026-10-12 by cloning each repository (`git clone --filter=blob:none`) and reading the file at the commit listed.
"File commit" = last commit that changed the file; "repo HEAD" = the default-branch commit read.
No code from these sources is copied into this project. Libraries are used only through their public APIs.

| Source | File | File commit | Repo HEAD read | License | Used for | Not copied |
|---|---|---|---|---|---|---|
| lifelines (CamDavidsonPilon/lifelines) | `docs/Survival Regression.rst` | `d9b20adbde7a74402d0a1428a2df5f0d0bb19fb1` (2024-01-13) | `7a8fc34a013ecd79fa405017b89e1697c1cc6e17` | MIT | Planned (6b, after approval): duration/event data format, `LogNormalAFTFitter`, `predict_survival_function` | Rossi example data and variables |
| scikit-survival (sebp/scikit-survival) | `doc/user_guide/evaluating-survival-models.ipynb` | `3003362787c5f53b6376a39f5fa503497dede25b` (2026-09-13) | `ca0c2bd6ed19334d9cb357e309c38d730cac8cdc` | **GPL-3.0** | Concepts in 6a: IPCW (`concordance_index_ipcw`), Brier / integrated Brier, KM baseline, horizon `tau` within follow-up | Random `train_test_split`; its simulated independent-censoring setup (does not hold for stale U); no code, not a dependency |
| statsmodels (statsmodels/statsmodels) | `examples/python/ordinal_regression.py` | `37d7ac01d76aebcc1c1e2f6fee7828c706b97608` (2026-07-28) | `35a8e0b7483211f5be7e60926be082136263cac3` | BSD-3-Clause | Reserved for 3b (not approved this round): `OrderedModel` keeps the 1–5 star order as a sensitivity | Example variables (student data); any causal reading |
| scikit-learn (scikit-learn/scikit-learn) | `examples/model_selection/plot_cv_indices.py` | `3e127a3d5cb9ff89fcf61260c4d082663695fec4` (2024-07-22) | `bebaf70573b6fe756bc93aca5534f3191c18c4eb` | BSD-3-Clause | Stage 5 contrast: `TimeSeriesSplit` orders folds by time | `TimeSeriesSplit` itself — it splits by row position and does not enforce label availability or frozen seller snapshots, so stage 5 builds folds by purchase date and delivery date |
| scikit-learn | `examples/calibration/plot_calibration_curve.py` | `5eacafaa24ce3471fd0712a8f2bde6625e5c9dcf` (2026-10-09) | `bebaf70573b6fe756bc93aca5534f3191c18c4eb` | BSD-3-Clause | Background for the calibration finding (decile reliability) | `CalibratedClassifierCV` with internal CV (would mix time periods); recalibration not done |

Package availability checked with `pip index versions`: lifelines 0.30.3, scikit-survival 0.28.0. Neither is installed yet.

## Stage 7

- Angelopoulos, A. N. & Bates, S. (2021). *A Gentle Introduction to Conformal Prediction and Distribution-Free Uncertainty Quantification.* https://arxiv.org/abs/2107.07511 — split conformal; the marginal guarantee rests on exchangeability of calibration and test scores.
- scikit-learn `QuantileRegressor` (HiGHS solver) for the linear quantile regression; versions in `requirements-tested.txt`.
