# Stage 7 — Promised-Date Policies (parts 1–2)

> Exploratory extension, pre-registered in `config/date_policy.yaml` (SHA-256 in `outputs/stage7/PREREGISTRATION_SHA256.txt`). Policies are fitted and calibrated with information known at 2018-04-01, frozen, and scored on purchases from 2018-04-01. Population: single-seller orders with a final on-time/late outcome — results do not cover canceled or unconfirmed orders.

## Splits

| rows | orders | late_rate | first_purchase | last_purchase |
|---|---|---|---|---|
| fit | 25666 | 0.03666328995558326 | 2017-01-07 13:29:22 | 2017-09-30 23:59:15 |
| cal_A | 17056 | 0.087359287054409 | 2017-10-01 00:03:33 | 2017-12-31 23:29:31 |
| cal_B | 16577 | 0.0697351752428063 | 2018-01-01 02:48:41 | 2018-03-29 01:12:21 |
| eval | 19950 | 0.042606516290726815 | 2018-04-01 00:11:32 | 2018-07-19 20:57:35 |

## Overall results (evaluation orders)

| target | policy | orders | coverage | mean_promised_days | median_promised_days | mean_overrun_days_when_missed |
|---|---|---|---|---|---|---|
| 0.90 | B0_state_quantile | 19950 | 93.9% | 20.31 | 19.0 | 8.19 |
| 0.90 | Q1_quantile_regression | 19950 | 89.5% | 16.86 | 16.0 | 7.15 |
| 0.90 | Q2_qr_conformal_A | 19950 | 96.4% | 22.87 | 22.0 | 9.35 |
| 0.90 | Q2_qr_conformal_B | 19950 | 96.3% | 22.64 | 21.0 | 9.24 |
| 0.90 | Olist_promise | 19950 | 95.7% | 24.44 | 24.0 | 9.01 |
| 0.95 | B0_state_quantile | 19950 | 97.3% | 25.33 | 23.0 | 9.73 |
| 0.95 | Q1_quantile_regression | 19950 | 93.8% | 19.92 | 18.0 | 7.90 |
| 0.95 | Q2_qr_conformal_A | 19950 | 98.3% | 28.27 | 27.0 | 10.74 |
| 0.95 | Q2_qr_conformal_B | 19950 | 98.1% | 27.38 | 26.0 | 10.31 |
| 0.95 | Olist_promise | 19950 | 95.7% | 24.44 | 24.0 | 9.01 |
| olist_matched | B0_state_quantile | 19950 | 94.9% | 21.40 | 20.0 | 8.45 |
| olist_matched | Q1_quantile_regression | 19950 | 90.6% | 17.44 | 16.0 | 7.28 |
| olist_matched | Q2_qr_conformal_A | 19950 | 96.9% | 23.91 | 23.0 | 9.58 |
| olist_matched | Q2_qr_conformal_B | 19950 | 96.8% | 23.53 | 22.0 | 9.61 |
| olist_matched | Olist_promise | 19950 | 95.7% | 24.44 | 24.0 | 9.01 |

## Conformal shifts (days added to the regression prediction)

| target | level | calibration | n | shift_days |
|---|---|---|---|---|
| 0.90 | 0.9 | A | 17056 | 6.02 |
| 0.90 | 0.9 | B | 16577 | 5.78 |
| 0.95 | 0.95 | A | 17056 | 8.35 |
| 0.95 | 0.95 | B | 16577 | 7.46 |
| olist_matched | 0.91 | A | 17056 | 6.47 |
| olist_matched | 0.91 | B | 16577 | 6.09 |

## Monthly coverage

| target | policy | 2018-04 | 2018-05 | 2018-06 | 2018-07 |
|---|---|---|---|---|---|
| 0.90 | B0_state_quantile | 93.5% | 91.0% | 97.4% | 97.5% |
| 0.90 | Olist_promise | 95.4% | 93.3% | 98.7% | 97.1% |
| 0.90 | Q2_qr_conformal_A | 95.7% | 95.2% | 98.5% | 98.2% |
| 0.90 | Q2_qr_conformal_B | 95.5% | 95.0% | 98.5% | 98.1% |
| 0.95 | B0_state_quantile | 96.9% | 96.3% | 98.7% | 98.2% |
| 0.95 | Olist_promise | 95.4% | 93.3% | 98.7% | 97.1% |
| 0.95 | Q2_qr_conformal_A | 97.7% | 98.0% | 99.2% | 99.0% |
| 0.95 | Q2_qr_conformal_B | 97.5% | 97.6% | 99.2% | 98.9% |
| olist_matched | B0_state_quantile | 94.4% | 92.4% | 98.0% | 97.5% |
| olist_matched | Olist_promise | 95.4% | 93.3% | 98.7% | 97.1% |
| olist_matched | Q2_qr_conformal_A | 96.2% | 95.9% | 98.7% | 98.3% |
| olist_matched | Q2_qr_conformal_B | 96.1% | 95.7% | 98.6% | 98.3% |

## Decision rules (as registered)

```json
{
  "0.90": {
    "level": 0.9,
    "Q2A_vs_B0": {
      "days_shorter": -2.5691729323308294,
      "coverage_drop_pts": -2.496240601503752,
      "keep_complex": false
    },
    "Q1_vs_B0": {
      "days_shorter": 3.448721804511276,
      "coverage_drop_pts": 4.401002506265672,
      "keep_complex": false
    },
    "months_unreliable": {
      "B0_state_quantile": [],
      "Q1_quantile_regression": [
        "2018-05"
      ],
      "Q2_qr_conformal_A": [],
      "Q2_qr_conformal_B": []
    },
    "calibration_mean_abs_monthly_gap_pts": {
      "A": 6.887703860584179,
      "B": 6.762402164794498
    },
    "calibration_A_better": false
  },
  "0.95": {
    "level": 0.95,
    "Q2A_vs_B0": {
      "days_shorter": -2.940200501253134,
      "coverage_drop_pts": -1.0125313283207982,
      "keep_complex": false
    },
    "Q1_vs_B0": {
      "days_shorter": 5.414987468671679,
      "coverage_drop_pts": 3.4335839598997553,
      "keep_complex": false
    },
    "months_unreliable": {
      "B0_state_quantile": [],
      "Q1_quantile_regression": [
        "2018-05"
      ],
      "Q2_qr_conformal_A": [],
      "Q2_qr_conformal_B": []
    },
    "calibration_mean_abs_monthly_gap_pts": {
      "A": 3.4783553802884892,
      "B": 3.2755644839587594
    },
    "calibration_A_better": false
  },
  "olist_matched": {
    "level": 0.9126,
    "Q2A_vs_B0": {
      "days_shorter": -2.5151879699248134,
      "coverage_drop_pts": -2.0250626566416075,
      "keep_complex": false
    },
    "Q1_vs_B0": {
      "days_shorter": 3.9571428571428555,
      "coverage_drop_pts": 4.3308270676691745,
      "keep_complex": false
    },
    "months_unreliable": {
      "B0_state_quantile": [],
      "Q1_quantile_regression": [
        "2018-05"
      ],
      "Q2_qr_conformal_A": [],
      "Q2_qr_conformal_B": []
    },
    "calibration_mean_abs_monthly_gap_pts": {
      "A": 6.030935548887106,
      "B": 5.930912366469218
    },
    "calibration_A_better": false,
    "B0_state_quantile_vs_Olist": {
      "days_shorter": 3.0425563909774453,
      "coverage_drop_pts": 0.8421052631578885,
      "shorter_with_coverage_loss_within_tolerance": true
    },
    "Q1_quantile_regression_vs_Olist": {
      "days_shorter": 6.999699248120301,
      "coverage_drop_pts": 5.172932330827063,
      "shorter_with_coverage_loss_within_tolerance": false
    },
    "Q2_qr_conformal_A_vs_Olist": {
      "days_shorter": 0.5273684210526319,
      "coverage_drop_pts": -1.182957393483719,
      "shorter_with_coverage_loss_within_tolerance": false
    }
  }
}
```

## Blocking checks

| check | expected | actual | pass |
|---|---|---|---|
| config matches the registered SHA-256 | 9c1ff876fb1777719a95cdb606b1f78be7989441b328a7b664dc8076a95b4747 | 9c1ff876fb1777719a95cdb606b1f78be7989441b328a7b664dc8076a95b4747 | True |
| stage 3 report is current | True | True | True |
| fit and calibration labels delivered before the freeze | True | True | True |
| fit, calibration and evaluation windows do not overlap | 0 | 0 | True |
| Olist's own estimate is not a model input | False | False | True |
| every seller snapshot holds only labels delivered before its time | True | True | True |
| Olist promise coverage on evaluation == 1 - stage-3 late rate | True | True | True |
| required_days > olist_promise_days exactly for late orders | True | True | True |
