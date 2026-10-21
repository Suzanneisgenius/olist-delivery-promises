> SUPERSEDED — historical copy, not the current release.

# Stage 4 browser checks

Pages tested (SHA-256): `weekly_review.html` 626bdf1c0e9f…, `data_quality.html` d603c45db792…, `model_report.html` 11e334434f23…

Run by `scripts/ui_check_stage4.py` (Playwright, headless Chromium) against the generated pages.
Developer evidence only; this is **not** the project owner's business UAT sign-off.

Result: **33 of 33 checks pass.** Screenshots: `outputs/stage4/screens/`.

| Case | Expected | Observed | Pass |
|---|---|---|---|
| pages under test == pages of the current stage-4 release (SHA-256) | [] | [] | yes |
| weekly_review.html light 1280px: no console or page errors | [] | [] | yes |
| weekly_review.html light 1280px: no page-wide horizontal overflow (px) | 0 | 0 | yes |
| weekly_review.html dark 1280px: no console or page errors | [] | [] | yes |
| weekly_review.html dark 1280px: no page-wide horizontal overflow (px) | 0 | 0 | yes |
| weekly_review.html light 390px: no console or page errors | [] | [] | yes |
| weekly_review.html light 390px: no page-wide horizontal overflow (px) | 0 | 0 | yes |
| data_quality.html light 1280px: no console or page errors | [] | [] | yes |
| data_quality.html light 1280px: no page-wide horizontal overflow (px) | 0 | 0 | yes |
| data_quality.html dark 1280px: no console or page errors | [] | [] | yes |
| data_quality.html dark 1280px: no page-wide horizontal overflow (px) | 0 | 0 | yes |
| data_quality.html light 390px: no console or page errors | [] | [] | yes |
| data_quality.html light 390px: no page-wide horizontal overflow (px) | 0 | 0 | yes |
| model_report.html light 1280px: no console or page errors | [] | [] | yes |
| model_report.html light 1280px: no page-wide horizontal overflow (px) | 0 | 0 | yes |
| model_report.html dark 1280px: no console or page errors | [] | [] | yes |
| model_report.html dark 1280px: no page-wide horizontal overflow (px) | 0 | 0 | yes |
| model_report.html light 390px: no console or page errors | [] | [] | yes |
| model_report.html light 390px: no page-wide horizontal overflow (px) | 0 | 0 | yes |
| model page: headline AP shown == test_metrics.csv | 0.123 | 0.123 | yes |
| model page: ROC AUC shown == test_metrics.csv | 0.761 | 0.761 | yes |
| model page: top-10% precision shown | 13.0% | 13.0% | yes |
| model page: top-10% recall shown | 30.5% | 30.5% | yes |
| model page: independent check says all match | True | True | yes |
| nav: model → data quality | data_quality.html | data_quality.html | yes |
| data-quality page: orders shown | 99,441 | 99,441 | yes |
| data-quality page: human-reviewed count == manual_check_sample.csv | True | True | yes |
| nav: data quality → weekly review | weekly_review.html | weekly_review.html | yes |
| weekly page: whole-window on-time shown | 92.92% | 92.92% | yes |
| weekly page: 'Largest decline' selects the worst pair | -9.58 | -9.58 | yes |
| weekly page: downloaded pair CSV has every state of that pair | 27 | 27 | yes |
| weekly page: every link target exists on disk (stage-2 links rebased) | [] | [] | yes |
| pages unchanged during the browser run (SHA-256) | [] | [] | yes |
