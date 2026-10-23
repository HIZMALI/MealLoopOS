from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from app.database import ROOT
from app.forecasting import (CONFIG, METHODS, NUMERIC_FEATURES, ForecastProblem, baseline, coverage, digest,
    evaluate, export_ridge, features, fingerprint, fit_ridge, predict_production, predict_ridge_state,
    production_state, quality_reasons, rates, rolling_predictions, select_method, targets, training_table,
    validate_dataset)
from app.parsing import parse_records


@pytest.fixture(scope="module")
def official_rows():
    records, _ = parse_records((ROOT / "data/raw/Food waste data school Finland 2024-2025.xlsx").read_bytes(), "official.xlsx", 135)
    return [{**r, "date": r["date"].isoformat()} for r in records]


@pytest.fixture(scope="module")
def evaluated(official_rows):
    return evaluate(official_rows)


def test_strict_paired_quality_exclusions_and_units(official_rows):
    c = coverage(official_rows)
    assert (c["total"], c["eligible"], c["excluded"]) == (155, 152, 3)
    assert [r["day_index"] for r in c["exclusions"]] == [18, 136, 151]
    assert coverage(official_rows[:135])["eligible"] == 134
    assert coverage(official_rows[135:])["eligible"] == 18
    assert np.allclose(targets(official_rows[0]), [10.205 * 1000 / 486, 29.5 * 1000 / 486])


@pytest.mark.parametrize("field,value", [("plate_waste_kg", None), ("kitchen_serving_waste_kg", None), ("diners", 0), ("diners", None), ("plate_waste_kg", -1)])
def test_bad_target_rows_never_enter_either_stream(official_rows, field, value):
    row = {**official_rows[0], field: value}
    assert quality_reasons(row)
    assert len(training_table([row, official_rows[1]])[0]) == 1


def test_exclusions_and_reported_values_never_repair_source(official_rows, evaluated):
    assert official_rows[135]["reported_plate_g_per_diner"] == pytest.approx(8.250034655376933)
    assert evaluated[0]["holdout_predictions"][0]["actual"] is None
    assert official_rows[17]["kitchen_serving_waste_kg"] is None
    assert official_rows[150]["reported_plate_waste_g"] == 6751


def test_features_are_prefix_only_and_do_not_include_actual_diners(official_rows):
    history = [r for r in official_rows[:60] if not quality_reasons(r)]
    feature = features(official_rows[60]["date"], official_rows[60]["menu"], history)
    assert set(feature) == set(NUMERIC_FEATURES + CONFIG["categorical_features"])
    assert "diners" not in feature and "phase" not in feature
    assert feature["past_plate_mean_10"] == pytest.approx(np.mean([targets(r)[0] for r in history[-10:]]))


def test_future_target_and_current_target_adversary(official_rows):
    original, _ = rolling_predictions(official_rows, 60, 85)
    changed = deepcopy(official_rows)
    for row in changed[70:]:
        row["plate_waste_kg"] *= 50
        row["kitchen_serving_waste_kg"] *= 30
        row["diners"] = 1
    altered, _ = rolling_predictions(changed, 60, 85)
    # Day 71's own target was corrupted; its predictions still cannot change.
    for a, b in zip(original[:11], altered[:11]):
        assert a["predictions"] == b["predictions"]
        assert a["history_last_day"] < a["day_index"]
    # Past observed outcomes may influence the NEXT service after they are known.
    assert original[11]["predictions"]["recent_mean_10"] != altered[11]["predictions"]["recent_mean_10"]


def test_training_fold_only_imputation_scaling_and_categories(official_rows):
    changed = deepcopy(official_rows)
    for row in changed[60:]:
        row["menu"] = 999
        row["date"] = "2030-12-31"
        row["plate_waste_kg"] *= 1000
    _, before = rolling_predictions(official_rows, 60, 61, ["ridge_10"])
    _, after = rolling_predictions(changed, 60, 61, ["ridge_10"])
    assert before == after
    state = before["ridge_10"]["state"]
    x, _ = training_table(official_rows[:60])
    expected = np.nanmedian(x[NUMERIC_FEATURES].to_numpy(), axis=0)
    assert np.allclose(state["imputer"], expected)
    filled = x[NUMERIC_FEATURES].fillna(dict(zip(NUMERIC_FEATURES, expected)))
    assert np.allclose(state["mean"], filled.mean().to_numpy())
    assert "999" not in state["categories"][2]
    assert before["ridge_10"]["fit_rows"] == 59


def test_all_training_cutoffs_and_observation_origins(evaluated):
    report, _ = evaluated
    assert [f["training"]["last_day"] for f in report["folds"]] == [60, 85, 110]
    assert [f["training"]["eligible"] for f in report["folds"]] == [59, 84, 109]
    for fold in report["folds"]:
        assert fold["training"]["end_date"] < fold["validation"]["start_date"]
        assert fold["validation"]["last_day"] <= 135
    for p in report["validation_predictions"] + report["holdout_predictions"]:
        assert p["history_last_day"] < p["day_index"]
        assert p["fit_cutoff_day"] < p["day_index"]
    assert all(p["fit_cutoff_day"] == 135 for p in report["holdout_predictions"])


def test_holdout_has_no_influence_on_selection_or_validation(official_rows, evaluated):
    changed = deepcopy(official_rows)
    for row in changed[135:]:
        row["plate_waste_kg"] *= 9
        row["kitchen_serving_waste_kg"] *= 7
    altered_report, altered_production = evaluate(changed)
    original, original_production = evaluated
    assert altered_report["validation_metrics"] == original["validation_metrics"]
    assert altered_report["validation_predictions"] == original["validation_predictions"]
    assert altered_report["selected_method"] == original["selected_method"]
    assert altered_report["holdout_fit_audit"] == original["holdout_fit_audit"]
    assert altered_report["holdout_predictions"][0]["predictions"] == original["holdout_predictions"][0]["predictions"]
    assert altered_production != original_production  # only AFTER frozen evaluation


def test_reproducibility_no_source_mutation_and_regression(official_rows, evaluated):
    before = deepcopy(official_rows)
    report, state = evaluate(official_rows)
    assert official_rows == before
    assert (report, state) == evaluated
    assert digest(report) == digest(evaluated[0])
    assert report["selected_method"] == "recent_mean_10"
    assert report["validation_metrics"]["recent_mean_10"]["combined"]["mae"] == pytest.approx(12.554173533637506)
    assert report["holdout_metrics"]["recent_mean_10"]["combined"]["mae"] == pytest.approx(8.730281863331307)
    assert report["production_training"]["eligible"] == 152


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("menu", [None, 999])
def test_missing_unknown_menu_fallback(official_rows, method, menu):
    state = production_state(official_rows, method)
    prediction, fallback = predict_production(state, "2025-04-14", menu)
    assert fallback
    assert prediction == rates(state["recent_mean"])


@pytest.mark.parametrize("method", METHODS)
def test_nonnegative_and_component_sum(official_rows, method):
    state = production_state(official_rows, method)
    result, _ = predict_production(state, "2025-04-14", 1)
    assert min(result.values()) >= 0
    assert result["combined"] == result["plate"] + result["kitchen"]
    assert rates([-10, 5]) == {"plate": 0, "kitchen": 5, "combined": 5}


def test_json_ridge_state_matches_pipeline_predict(official_rows):
    model = fit_ridge(official_rows[:135], 100)
    history = [r for r in official_rows[:135] if not quality_reasons(r)]
    feature = features("2025-03-17", 11, history)
    assert np.allclose(predict_ridge_state(export_ridge(model), feature), model.predict(pd.DataFrame([feature]))[0], atol=1e-10)
    state = export_ridge(model)
    state["coefficients"] = np.zeros_like(state["coefficients"]).tolist()
    state["intercept"] = [-100, -50]
    assert rates(predict_ridge_state(state, feature))["combined"] == 0


def test_selection_uses_combined_validation_and_deterministic_tie_break():
    scores = {m: {"combined": {"mae": 9}} for m in METHODS}
    assert select_method(scores) == METHODS[0]
    scores["ridge_100"]["combined"]["mae"] = 8
    assert select_method(scores) == "ridge_100"


def test_zero_targets_are_observations_not_missing(official_rows):
    row = {**official_rows[0], "plate_waste_kg": 0, "kitchen_serving_waste_kg": 0}
    assert not quality_reasons(row)
    assert np.array_equal(targets(row), [0, 0])


@pytest.mark.parametrize("problem", ["empty", "short", "missing-date", "unordered", "synthetic", "few-training", "few-holdout", "no-split"])
def test_blocked_datasets(official_rows, problem):
    rows = deepcopy(official_rows)
    source = SimpleNamespace(kind="measured")
    batch = SimpleNamespace(baseline_days=135)
    if problem == "empty": rows = []
    if problem == "short": rows = rows[:100]
    if problem == "missing-date": rows[0]["date"] = None
    if problem == "unordered": rows[0]["date"] = rows[1]["date"]
    if problem == "synthetic": source.kind = "synthetic"
    if problem == "few-training":
        for r in rows[:30]: r["diners"] = 0
    if problem == "few-holdout":
        for r in rows[135:152]: r["diners"] = 0
    if problem == "no-split": batch.baseline_days = None
    with pytest.raises(ForecastProblem):
        validate_dataset(batch, source, rows)


def test_fingerprint_changes_with_normalized_data_and_source(official_rows):
    batch = SimpleNamespace(sha256="raw", baseline_days=135, inspection={"verified_official_file": True})
    source = SimpleNamespace(key="official", kind="measured")
    original = fingerprint(batch, source, official_rows)
    changed = deepcopy(official_rows); changed[-1]["plate_waste_kg"] += 1
    assert original != fingerprint(batch, source, changed)
    source.kind = "synthetic"
    assert original != fingerprint(batch, source, official_rows)
