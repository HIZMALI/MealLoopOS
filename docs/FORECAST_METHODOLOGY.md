# Forecast methodology

Version **build02-v1**, quality policy **strict-paired-v1**. This protocol was implemented before inspecting holdout performance. No hyperparameters or candidate definitions were changed in response to the final holdout. Raw and normalized source records remain unchanged. See `MODEL_EVALUATION.md` and `evaluation/build_02_evaluation.json` for executed evidence.

## Forecast quantities and availability

For each eligible recorded school day, calculate two targets from primary measurements:

`plate_g_per_diner = plate_waste_kg × 1,000 / observed_diners`

`kitchen_g_per_diner = kitchen_serving_waste_kg × 1,000 / observed_diners`

Combined actuals and predictions are the sum of their plate and kitchen components. Both forecast components are clipped to zero from below **before** summing. There is no independently fitted combined model that could disagree with its components.

Historical observed attendance is required to calculate targets after service; it is **not a feature assumed available at planning time**. A future user supplies planned diners explicitly. `estimated_plate_kg = predicted_plate_g_per_diner × planned_diners / 1,000`, with the analogous kitchen calculation; combined estimated kg is the sum of those masses. Forecast g/diner is independent of the scenario diner count. No historical kg error is claimed as attendance-independent operational accuracy, and no production quantities or prepared servings are inferred.

## Strict quality policy

All three targets share the **same eligible rows**. Exclude the whole modeling day if either primary mass is missing, nonfinite, or negative, if diners are missing/nonpositive, or if any recorded conflict/duplicate flag is present. Conversion-from-grams and missing-menu notes alone do not invalidate an otherwise observed target. No target is imputed. All source records and notes remain available; exclusion is an explicit modeling decision, not a source correction.

Official exclusions are day 18 / source row 19 (missing kitchen mass), day 136 / row 137 (both redundant per-diner conflicts), and day 151 / row 152 (redundant gram/kg and plate-per-diner conflicts). Even when a redundant field alone conflicts, this conservative policy excludes the whole paired observation rather than assert that the primary kg field is scientifically correct. Reported per-diner fields are never authoritative targets.

The official workbook has **152 eligible days**, comprising **134 of 135 baseline days** and **18 of 20 holdout days**. Dates must exist, be unique, and strictly increase in original source order. A batch lacking those chronology requirements is blocked rather than assigned invented dates. Menu can be missing. The current fixed protocol requires exactly 135 explicitly assigned baseline days, at least 40 eligible observations in the first 60-day training prefix, and at least five eligible observations in each validation window and holdout. It supports at most 1,000 recorded days. These constraints are deliberate; arbitrary imports remain usable in the descriptive dashboard.

## Predefined candidate methods

| Method ID | Prediction at each forecast origin |
| --- | --- |
| `recent_mean_10` | Arithmetic component means of the latest 10 eligible *observed school days* |
| `menu_mean` | Arithmetic component means of all earlier eligible observations with the current menu; recent-10 fallback if the menu is missing/unseen |
| `expanding_mean` | Arithmetic component means of every earlier eligible observation, recomputed as history advances |
| `ridge_10` | Two-output scikit-learn Pipeline Ridge regression, alpha 10 |
| `ridge_100` | Same pipeline, alpha 100 |

There are no post-holdout candidate searches. For operational consistency, every method uses the recent-10 fallback for missing/unseen menus; the expanding mean and Ridge therefore also have that explicit fallback. Window size 10, the two alphas, and cutoffs are fixed in the versioned configuration, not optimized against holdout outcomes. A single method is selected jointly for the two components using combined MAE; it need not be the best method for each individual component.

Historical menu means are day-weighted rates, not diner-weighted aggregate ratios. This aligns them with the equally weighted per-day forecasting loss. The descriptive aggregate g/diner remains diner-weighted and is a different estimand.

## Planning-time Ridge features and transformations

Numeric features are the past 10 eligible days' mean plate and kitchen g/diner. Categorical features are planned service weekday, calendar month, and menu ID. Missing menu is represented explicitly; unseen/missing menus use the documented recent-mean fallback. Future calendar categories unseen during fitting are ignored by the one-hot encoder. No actual same-day mass, actual attendance, intervention label, future target, day-of-study trend proxy, or production quantity enters the feature matrix.

Training features for each historical row are constructed only from earlier eligible rows. The first eligible row has no past numeric history: `SimpleImputer(strategy="median")` learns its fills from the training fold's already available feature matrix, followed by `StandardScaler`. A `ColumnTransformer` one-hot encodes the categorical columns with `handle_unknown="ignore"` and dense output. The resulting scikit-learn `Pipeline` fits a multi-output `Ridge(alpha=10 or 100, solver="svd", random_state=42)`. SVD is deterministic; the explicit seed documents reproducibility, not stochastic accuracy.

All imputer medians, scales, categories, and Ridge coefficients are fitted **only on that training prefix**. They remain frozen through its validation window. A validation/holdout day's calendar and planned menu are known inputs; its observed targets enter history only *after* that day's predictions. This is distinct from refitting the model after every service.

The [scikit-learn guidance on leakage](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage) supports fitting preprocessing only on training data and using pipelines. [Ridge documentation](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html) describes the regularized regression used here. The explicit chronological splits below follow the expanding-prefix principle documented in [TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html); this implementation enumerates source-row windows directly because school days are not uniformly spaced calendar days.

## Selection within baseline only

| Fold | Recorded training prefix | Strict eligible train | Validation source days | Eligible validation |
| --- | --- | ---: | --- | ---: |
| 1 | Days 1–60 | 59 | Days 61–85 | 25 |
| 2 | Days 1–85 | 84 | Days 86–110 | 25 |
| 3 | Days 1–110 | 109 | Days 111–135 | 25 |

The full baseline spans **2024-08-08 to 2025-03-14**. Training cutoffs use recorded-day positions before quality filtering so missing days cannot shift a boundary. Every validation date follows all dates in its fit prefix. Baselines update from prefix history one step at a time. Ridge fits once per fold, while its history features update from prior eligible observations. Earlier validation observations are allowed in a later fold's training prefix because they are then in the past.

Pool the **75 non-overlapping validation predictions** for each method. For eligible daily errors `eᵢ = predictionᵢ − actualᵢ`, `MAE = mean(abs(eᵢ))`, `RMSE = sqrt(mean(eᵢ²))`, all in g/diner. Each eligible day has equal weight, independent of attendance. Compute all three target metrics and sample counts. Select the method with minimum pooled **combined MAE**; exact ties follow predefined candidate order (simpler baselines first). RMSE and per-component errors are reported, not additional selection objectives.

## Final holdout, frozen choice

Before evaluating any day 136–155, freeze the selected method/configuration using only baseline validation. Fit Ridge candidates' holdout pipelines once on all **134 eligible baseline samples** through **2025-03-14**. The 20 recorded holdout services span **2025-03-17 through 2025-04-11**; 18 have eligible paired actuals.

At each holdout service, predict before reading its target. Prior eligible holdout outcomes may enter a later service's history because those services have completed. Current/future outcomes, including attendance-derived rates, may not. Excluded days have forecasts but no scored actuals and never update history. Every prediction records its fit cutoff, latest eligible history day, actual (or null), inclusion decision, and reasons. Predictions on excluded days do not imply their targets were valid.

Candidate holdout metrics are reported for transparency, but **do not alter selection**. Ridge preprocessing/coefficients are not refitted or tuned on holdout. This is a one-day-ahead rolling-origin challenge, not a 20-day fixed-origin forecast. A fixed-origin forecast without any new observations could have different performance. The holdout contains an external artist-designed intervention and distribution shift, not a randomized test of this software or proof of its impact.

## Separate production artifact and future scenarios

Only after frozen evaluation, prepare a distinct production state on **all 152 eligible observations** through **2025-04-11**, retaining the baseline-selected method. If Ridge is selected, its production pipeline is independently refitted on all eligible rows; if a baseline is selected, persist its all-history/recent/menu statistics. This broader fit never substitutes for historical evaluation predictions.

Persist only inert JSON numeric state. Ridge state contains imputer medians, scaler means/scales, categorical levels, coefficients, and intercepts; tests compare its numeric JSON prediction with the fitted Pipeline. No pickle/joblib object is loaded. Forecast/status requests reuse this state across process restarts and never train. Dataset fingerprint, raw-file hash, source kind, baseline split, all normalized fields/audit flags, configuration, algorithm version, and relevant library versions distinguish artifacts. Historical scenario runs retain their original artifact IDs.

Future date must be later than the last recorded date. A request means the **next observed service after available history**, with no invented intermediate observations or recursive forecasts. Planned diners must be an integer from 1 to 1,000,000. Forecast menu accepts missing or unseen identifiers (1–10,000) for explicit fallback, while the measured-data import schema remains 1–25. A date gap over 14 calendar days triggers a stale-history warning. This is a disclosure threshold, not a validated horizon guarantee; even smaller gaps have limited evidence. The present historical workbook is old relative to current planning dates, so operational reliability is unestablished.

Synthetic batches are blocked from training/evaluation and cannot inherit a measured batch's artifact. The bundled fixture also retains its provenance mislabeling guard. Modified/unverified measured datasets remain explicitly user-supplied and must meet the same protocol constraints.

## Reproducibility and limits

Run `.venv/Scripts/python.exe scripts/evaluate_forecasts.py` after importing the official workbook. The command uses normalized SQLite records, executes evaluation afresh, compares fresh evidence/state to the persisted artifact, and writes deterministic `docs/evaluation/build_02_evaluation.json`. No network service or paid API is called. Exact package versions are in the backend lock and evidence configuration. Algorithm changes require a version bump before an existing artifact can be reused.

No calibrated confidence percentages or intervals are provided. Waste forecasts do not establish money/carbon savings, production quantities or causal effects. Decision Studio treats production planning separately under explicit assumptions. Ridge fails to beat the recent-history baseline on combined validation MAE. The selected baseline's holdout results do **not demonstrate reliable operational forecasting**: the sample is small, single-site, intervention-shifted, and chronologically narrow. Further prospective/external validation is required.

Dataset attribution: Arja Kuusisto, Jenni Latva, Ella Wilén (2026), *Food waste dataset: secondary school in Finland 2024–2025*, [Zenodo record](https://zenodo.org/records/20825233), [DOI 10.5281/zenodo.20825233](https://doi.org/10.5281/zenodo.20825233), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Original workbook unchanged; normalized targets, exclusions, forecasts, and evaluation summaries are MealLoop OS derivatives, without implied endorsement.
