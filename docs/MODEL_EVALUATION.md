# Executed model evaluation

Executed October 23, 2026 (Europe/Istanbul), using the normalized, checksum-verified official measured batch. All figures below are computed by the committed protocol; no placeholders or invented accuracy percentages are used.

Model ID: `ml02-e1184f5007c6d747-36ecbc6bdc`. Algorithm: `build02-v1`. Quality policy: `strict-paired-v1`.

Normalized dataset fingerprint: `e1184f5007c6d7473e49c268c56a6ee5dc3ab80d8fb1aa4ee4216009a6016366`.

Raw workbook SHA-256: `2ffad746b7ed5d536a0c99c37d8e249230d95d5fb2d041d85d01b69499f99624`.

## Selection result

**Selected: Recent 10-day mean (`recent_mean_10`).** Selection minimizes pooled combined MAE on the 75 baseline-validation days only; the final holdout does not select or tune the model. A single method serves both components and their sum. The best individual plate model can differ from the combined-loss winner.

**Ridge did not improve combined validation MAE. Reliable operational forecasting has not been established by these results.** This is one small school dataset with an external intervention in the holdout; future dates and other schools have not been validated. The last observation is April 11, 2025, so current-date scenarios are explicitly flagged for stale history.

## Candidate metrics

Every MAE and RMSE is **g/diner**, weighted equally per eligible school day. Combined errors are computed from component-consistent predictions, not by adding component errors. All candidates use identical quality-based scoring coverage.

### Baseline chronological validation

| Candidate | Plate MAE | Plate RMSE | Kitchen MAE | Kitchen RMSE | Combined MAE | Combined RMSE | n |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Expanding-history mean | 5.489079 | 7.241447 | 13.151555 | 16.447944 | 14.320622 | 17.860799 | 75 |
| Historical menu mean | 5.430283 | 7.099651 | 14.583679 | 19.666762 | 16.856734 | 20.914258 | 75 |
| Recent 10-day mean **(selected)** | 5.668228 | 7.434408 | 10.939545 | 15.758898 | 12.554174 | 17.108574 | 75 |
| Ridge · alpha 10 | 5.783545 | 7.062232 | 14.841200 | 18.487555 | 17.733050 | 21.516084 | 75 |
| Ridge · alpha 100 | 5.526340 | 7.072233 | 14.019990 | 17.166775 | 15.375810 | 18.984891 | 75 |

### Final one-day-ahead intervention holdout

| Candidate | Plate MAE | Plate RMSE | Kitchen MAE | Kitchen RMSE | Combined MAE | Combined RMSE | n |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Expanding-history mean | 7.367007 | 8.425375 | 13.124316 | 13.891812 | 16.242887 | 17.773293 | 18 |
| Historical menu mean | 4.365153 | 5.354452 | 14.144095 | 16.536817 | 17.154425 | 20.592747 | 18 |
| Recent 10-day mean **(selected)** | 6.151905 | 7.398766 | 7.949256 | 10.600837 | 8.730282 | 10.544463 | 18 |
| Ridge · alpha 10 | 5.588262 | 6.930118 | 13.630476 | 14.625122 | 17.380989 | 19.175061 | 18 |
| Ridge · alpha 100 | 7.060803 | 8.141133 | 12.366761 | 13.086200 | 15.737805 | 17.281556 | 18 |

## Coverage and chronology

| Stage | Source days | Date range | Eligible | Excluded |
| --- | --- | --- | ---: | ---: |
| Fold ending 60: training | 1–60 | 2024-08-08 – 2024-11-06 | 59 | 1 |
| Fold ending 60: validation | 61–85 | 2024-11-07 – 2024-12-12 | 25 | 0 |
| Fold ending 85: training | 1–85 | 2024-08-08 – 2024-12-12 | 84 | 1 |
| Fold ending 85: validation | 86–110 | 2024-12-13 – 2025-01-31 | 25 | 0 |
| Fold ending 110: training | 1–110 | 2024-08-08 – 2025-01-31 | 109 | 1 |
| Fold ending 110: validation | 111–135 | 2025-02-03 – 2025-03-14 | 25 | 0 |
| Frozen holdout fit: baseline only | 1–135 | 2024-08-08 – 2025-03-14 | 134 | 1 |
| Final holdout scoring | 136–155 | 2025-03-17 – 2025-04-11 | 18 | 2 |
| Separate production state after evaluation | 1–155 | 2024-08-08 – 2025-04-11 | 152 | 3 |

The production state includes all eligible history only after selection/evaluation have finished. Its 152-day coverage must not be confused with the frozen 134-day holdout training fit. The 75 validation predictions have no overlapping scoring windows. The first missing observation occurs in training, so every validation window has 25 eligible targets.

## Explicit target exclusions

| Day | Source row | Date | Modeling exclusion |
| ---: | ---: | --- | --- |
| 18 | 19 | 2024-09-02 | invalid_or_missing_kitchen_serving_waste_kg |
| 136 | 137 | 2025-03-17 | plate_per_diner_conflict, kitchen_per_diner_conflict |
| 151 | 152 | 2025-04-07 | plate_kg_g_conflict, plate_per_diner_conflict |

Both component targets are excluded together for these days. No original measurement, conflicting reported value, or source note is edited. Predictions for excluded holdout days remain in the evidence with `actual: null`, explicit reasons, and no contribution to metrics/history.

## Protocol interpretation

The recent baseline, menu means, expanding mean, and Ridge lag features can use earlier eligible evaluation outcomes only after their service day has completed. Ridge preprocessing/coefficients stay fixed at each training cutoff. This is rolling-origin one-day-ahead evaluation, not a fixed-origin 20-day-ahead forecast. It cannot support a claim about the accuracy of long-gap forecasts without new observations.

The holdout includes artist-designed interventions external to MealLoop OS. Differences between validation and holdout error can reflect distribution shift, target variability, menu/exposure mix, and sampling. They are not evidence of software-caused waste prevention, improved impact, or guaranteed accuracy.

Historical targets divide recorded kg by observed diners after service. Forecast kg outputs instead multiply predicted g/diner by the user-provided planned attendance. No historical attendance-conditioned kg error is presented as achievable operational accuracy. Confidence intervals and savings are not claimed.

## Reproduce and inspect

Run `.venv/Scripts/python.exe scripts/evaluate_forecasts.py` from the repository root after importing the official workbook. It executes evaluation afresh, compares it to the persisted version, and emits [the machine-readable evidence](evaluation/build_02_evaluation.json). The file includes all candidate metrics, fold windows/fit audits, every validation and holdout prediction/actual, exclusions, source provenance, model settings, package versions, and fingerprints.

Two executions on the verified environment produced the same evidence bytes (SHA-256 `0d5bdc9386b3661502a48b69d5fc602bbf13874dba16ea852bc8a85dbc82092b`). The evidence excludes wall-clock timestamps and DB primary keys so those do not perturb scientific results. Numerical results across other dependency/BLAS versions may vary; versions participate in artifact identity.

See [FORECAST_METHODOLOGY.md](FORECAST_METHODOLOGY.md) for exact rules and [REPRODUCIBILITY.md](REPRODUCIBILITY.md) for release verification.

Attribution: Arja Kuusisto, Jenni Latva, Ella Wilén (2026), *Food waste dataset: secondary school in Finland 2024–2025*. [Zenodo](https://zenodo.org/records/20825233), [DOI 10.5281/zenodo.20825233](https://doi.org/10.5281/zenodo.20825233), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Original workbook unchanged; targets, quality exclusions, forecasts, and evaluation summaries are derived representations.
