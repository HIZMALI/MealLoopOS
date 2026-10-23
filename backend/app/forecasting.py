"""Deterministic one-step forecasts. Only prefix history may construct features.

Evaluation fits are frozen at each training cutoff; earlier eligible evaluation
outcomes enter history only after their prediction. Production fits are separate.
No executable/pickled objects are written: fitted numeric state is JSON only.
"""
import hashlib
import json
from collections import Counter
from datetime import date
from importlib.metadata import version

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

VERSION = "build02-v1"
POLICY = "strict-paired-v1"
METHODS = ["recent_mean_10", "menu_mean", "expanding_mean", "ridge_10", "ridge_100"]
LABELS = {"recent_mean_10": "Recent 10-day mean", "menu_mean": "Historical menu mean",
          "expanding_mean": "Expanding-history mean", "ridge_10": "Ridge · alpha 10", "ridge_100": "Ridge · alpha 100"}
NUMERIC_FEATURES = ["past_plate_mean_10", "past_kitchen_mean_10"]
CATEGORICAL_FEATURES = ["weekday", "month", "menu"]
CONFIG = {"version": VERSION, "quality_policy": POLICY, "methods": METHODS,
    "fold_train_cutoffs": [60, 85, 110], "fold_validation_days": 25, "history_window": 10,
    "ridge_alphas": [10.0, 100.0], "ridge_solver": "svd", "random_state": 42,
    "selection": "pooled baseline-validation combined MAE; ties follow candidate order",
    "numeric_features": NUMERIC_FEATURES, "categorical_features": CATEGORICAL_FEATURES,
    "nonnegative": "clip each component at zero, then sum", "unknown_menu": "recent_mean_10 fallback",
    "libraries": {name: version(name) for name in ("scikit-learn", "numpy", "pandas")}}


class ForecastProblem(ValueError):
    pass


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def snapshot(records):
    """Do not depend on DB primary keys: scientific fingerprints survive reimport."""
    keys = ["day_index", "source_row", "date", "menu", "diners", "plate_waste_kg", "kitchen_serving_waste_kg",
            "reported_plate_waste_g", "reported_plate_g_per_diner", "reported_kitchen_g_per_diner", "issues", "phase"]
    rows = []
    for r in records:
        item = {key: getattr(r, key) for key in keys}
        item["date"] = r.date.isoformat() if r.date else None
        rows.append(item)
    return rows


def fingerprint(batch, source, rows):
    return digest({"raw_sha256": batch.sha256, "baseline_days": batch.baseline_days,
        "source_key": source.key, "source_kind": source.kind,
        "verified_official_file": batch.inspection.get("verified_official_file", False), "rows": rows})


def quality_reasons(row):
    reasons = []
    for field in ("plate_waste_kg", "kitchen_serving_waste_kg"):
        value = row[field]
        if value is None or not np.isfinite(value) or value < 0:
            reasons.append(f"invalid_or_missing_{field}")
    n = row["diners"]
    if n is None or not np.isfinite(n) or n <= 0:
        reasons.append("missing_or_nonpositive_diners")
    for issue in row["issues"]:
        if "conflict" in issue or "duplicate" in issue:
            reasons.append(issue)
    return reasons


def targets(row):
    return np.array([row["plate_waste_kg"], row["kitchen_serving_waste_kg"]], dtype=float) * 1000 / row["diners"]


def rates(values):
    p, k = np.maximum(np.asarray(values, dtype=float), 0)
    return {"plate": float(p), "kitchen": float(k), "combined": float(p + k)}


def validate_dataset(batch, source, rows):
    if source.kind != "measured":
        raise ForecastProblem("Synthetic batches cannot train or supply scientific forecast evidence. Select a measured batch.")
    if not rows:
        raise ForecastProblem("This batch has no normalized records.")
    if len(rows) > 1000:
        raise ForecastProblem("Build 02 evaluation supports at most 1,000 school-day records.")
    dates = [r["date"] for r in rows]
    if any(d is None for d in dates) or any(a >= b for a, b in zip(dates, dates[1:])):
        raise ForecastProblem("Forecast validation needs unique, strictly chronological recorded dates. Source records remain unchanged.")
    if [r["day_index"] for r in rows] != list(range(1, len(rows) + 1)):
        raise ForecastProblem("Day indices must be contiguous in source order.")
    if batch.baseline_days != 135 or len(rows) <= 135:
        raise ForecastProblem("This Build 02 protocol requires 135 explicitly assigned baseline days and a later holdout (official data: 20 days).")
    if sum(not quality_reasons(r) for r in rows[:60]) < 40:
        raise ForecastProblem("Insufficient strict-quality history: the initial 60-day training window needs at least 40 eligible days.")
    for start, stop in [(60, 85), (85, 110), (110, 135), (135, len(rows))]:
        if sum(not quality_reasons(r) for r in rows[start:stop]) < 5:
            raise ForecastProblem("Insufficient strict-quality evaluation data: each validation window and holdout needs at least five eligible days.")


def features(service_date, menu, history):
    observed = date.fromisoformat(service_date)
    past = np.mean([targets(r) for r in history[-10:]], axis=0) if history else [np.nan, np.nan]
    return {"past_plate_mean_10": float(past[0]), "past_kitchen_mean_10": float(past[1]),
            "weekday": str(observed.weekday()), "month": str(observed.month), "menu": str(menu) if menu is not None else "missing"}


def training_table(rows):
    history, x, y = [], [], []
    for row in rows:
        if quality_reasons(row):
            continue
        x.append(features(row["date"], row["menu"], history))
        y.append(targets(row))
        history.append(row)
    return pd.DataFrame(x), np.asarray(y)


def fit_ridge(rows, alpha):
    x, y = training_table(rows)
    preprocessing = ColumnTransformer([
        ("history", Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), NUMERIC_FEATURES),
        ("calendar_menu", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
    ])
    model = Pipeline([("preprocess", preprocessing), ("ridge", Ridge(alpha=alpha, solver="svd", random_state=42))])
    model.fit(x, y)
    return model


def export_ridge(model):
    pre = model.named_steps["preprocess"]
    numeric = pre.named_transformers_["history"]
    return {"imputer": numeric.named_steps["impute"].statistics_.tolist(),
            "mean": numeric.named_steps["scale"].mean_.tolist(), "scale": numeric.named_steps["scale"].scale_.tolist(),
            "categories": [c.tolist() for c in pre.named_transformers_["calendar_menu"].categories_],
            "coefficients": model.named_steps["ridge"].coef_.tolist(), "intercept": model.named_steps["ridge"].intercept_.tolist()}


def predict_ridge_state(state, feature):
    numeric = np.array([feature[f] for f in NUMERIC_FEATURES], dtype=float)
    numeric = np.where(np.isnan(numeric), state["imputer"], numeric)
    encoded = ((numeric - np.asarray(state["mean"])) / np.asarray(state["scale"])).tolist()
    for field, categories in zip(CATEGORICAL_FEATURES, state["categories"]):
        encoded.extend(float(feature[field] == category) for category in categories)
    return np.asarray(state["coefficients"]) @ np.asarray(encoded) + np.asarray(state["intercept"])


def baseline(method, history, menu):
    recent = np.mean([targets(r) for r in history[-10:]], axis=0)
    if menu is None or menu not in {r["menu"] for r in history}:
        return recent
    if method == "recent_mean_10":
        return recent
    if method == "menu_mean":
        return np.mean([targets(r) for r in history if r["menu"] == menu], axis=0)
    return np.mean([targets(r) for r in history], axis=0)


def rolling_predictions(rows, cutoff, stop, methods=METHODS):
    """Ridge weights frozen at cutoff; history advances after each prediction."""
    training = rows[:cutoff]
    models = {method: fit_ridge(training, float(method.split("_")[1])) for method in methods if method.startswith("ridge_")}
    history = [r for r in training if not quality_reasons(r)]
    predictions = []
    for row in rows[cutoff:stop]:
        reasons = quality_reasons(row)
        item = {"day_index": row["day_index"], "source_row": row["source_row"], "date": row["date"],
            "included": not reasons, "exclusions": reasons, "actual": None, "predictions": {},
            "history_last_day": history[-1]["day_index"], "fit_cutoff_day": cutoff}
        feature = pd.DataFrame([features(row["date"], row["menu"], history)])
        known_menu = row["menu"] is not None and row["menu"] in {r["menu"] for r in history}
        for method in methods:
            value = models[method].predict(feature)[0] if method in models and known_menu else baseline(method, history, row["menu"])
            item["predictions"][method] = rates(value)
        if not reasons:
            item["actual"] = rates(targets(row))
            history.append(row)  # current target becomes visible only AFTER its forecast
        predictions.append(item)
    audits = {method: {"fit_cutoff_day": cutoff, "fit_rows": len(training_table(training)[0]),
        "state": export_ridge(model)} for method, model in models.items()}
    return predictions, audits


def score(predictions, method):
    included = [p for p in predictions if p["included"]]
    result = {"n": len(included)}
    for target in ("plate", "kitchen", "combined"):
        error = np.array([p["predictions"][method][target] - p["actual"][target] for p in included])
        result[target] = {"mae": float(np.mean(np.abs(error))), "rmse": float(np.sqrt(np.mean(error ** 2)))}
    return result


def select_method(metrics):
    return min(METHODS, key=lambda method: (metrics[method]["combined"]["mae"], METHODS.index(method)))


def coverage(rows):
    excluded = [{"day_index": r["day_index"], "source_row": r["source_row"], "date": r["date"],
                 "reasons": quality_reasons(r)} for r in rows if quality_reasons(r)]
    return {"total": len(rows), "eligible": len(rows) - len(excluded), "excluded": len(excluded),
            "exclusions": excluded, "reason_counts": dict(Counter(reason for r in excluded for reason in r["reasons"]))}


def period(rows):
    return {"first_day": rows[0]["day_index"], "last_day": rows[-1]["day_index"],
        "start_date": rows[0]["date"], "end_date": rows[-1]["date"], **coverage(rows)}


def production_state(rows, method):
    eligible = [r for r in rows if not quality_reasons(r)]
    known = sorted({r["menu"] for r in eligible if r["menu"] is not None})
    state = {"method": method, "known_menus": known, "recent_mean": np.mean([targets(r) for r in eligible[-10:]], axis=0).tolist(),
        "global_mean": np.mean([targets(r) for r in eligible], axis=0).tolist(),
        "menu_means": {str(m): np.mean([targets(r) for r in eligible if r["menu"] == m], axis=0).tolist() for m in known},
        "training": period(rows), "last_observation_date": rows[-1]["date"]}
    if method.startswith("ridge_"):
        state["ridge"] = export_ridge(fit_ridge(rows, float(method.split("_")[1])))
    return state


def predict_production(state, service_date, menu):
    unknown = menu is None or menu not in state["known_menus"]
    if unknown or state["method"] == "recent_mean_10":
        values = state["recent_mean"]
    elif state["method"] == "menu_mean":
        values = state["menu_means"][str(menu)]
    elif state["method"] == "expanding_mean":
        values = state["global_mean"]
    else:
        observed = date.fromisoformat(service_date)
        feature = dict(zip(NUMERIC_FEATURES, state["recent_mean"]))
        feature.update(weekday=str(observed.weekday()), month=str(observed.month), menu=str(menu))
        values = predict_ridge_state(state["ridge"], feature)
    return rates(values), unknown


def evaluate(rows):
    validation, folds = [], []
    for cutoff in CONFIG["fold_train_cutoffs"]:
        predictions, audits = rolling_predictions(rows, cutoff, cutoff + 25)
        validation.extend(predictions)
        folds.append({"training": period(rows[:cutoff]), "validation": period(rows[cutoff:cutoff + 25]), "ridge_fit_audit": audits,
                      "metrics": {method: score(predictions, method) for method in METHODS}})
    validation_metrics = {method: score(validation, method) for method in METHODS}
    selected = select_method(validation_metrics)  # frozen BEFORE holdout evaluation
    holdout, fit_audits = rolling_predictions(rows, 135, len(rows))
    holdout_metrics = {method: score(holdout, method) for method in METHODS}
    report = {"version": VERSION, "quality_policy": POLICY, "configuration": CONFIG,
        "selected_method": selected, "selected_label": LABELS[selected], "method_labels": LABELS,
        "selection_rule": CONFIG["selection"], "baseline_period": period(rows[:135]),
        "holdout_period": period(rows[135:]), "production_training": period(rows),
        "folds": folds, "validation_metrics": validation_metrics, "holdout_metrics": holdout_metrics,
        "validation_predictions": validation, "holdout_predictions": holdout, "holdout_fit_audit": fit_audits,
        "limitations": ["Small single-school observational dataset; reliability at other schools or dates is unestablished.",
            "Holdout includes an external artist-designed intervention and distribution shift; it is not evidence of MealLoop OS impact.",
            "One-day-ahead rolling-origin evaluation: earlier eligible holdout outcomes enter later histories, never the current/future outcome.",
            "Future attendance is an explicit user assumption used only to convert g/diner into estimated kg.",
            "No calibrated confidence interval, guaranteed savings, production quantity, or optimization is provided."]}
    return report, production_state(rows, selected)
