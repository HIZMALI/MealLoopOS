"""Dataset-scoped JSON artifacts. No fit occurs on prediction or status requests."""
import threading
from datetime import date, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from .forecast_schemas import BatchRequest, Evaluation, ForecastRequest, ForecastResult, ModelMetadata, ModelStatus, SavedForecast
from .forecasting import (CONFIG, VERSION, ForecastProblem, digest, evaluate, fingerprint,
                          predict_production, snapshot, validate_dataset)
from .models import DailyRecord, ForecastArtifact, ForecastRun, ImportBatch, SourceDataset

CONFIG_KEY = digest(CONFIG)


def load_data(session, batch_id=None):
    batch = session.get(ImportBatch, batch_id) if batch_id else session.scalar(select(ImportBatch).order_by(ImportBatch.id.desc()).limit(1))
    if batch is None:
        raise HTTPException(404, detail={"message": "Import a measured dataset first, or select an existing batch."})
    source = session.get(SourceDataset, batch.source_id)
    records = session.scalars(select(DailyRecord).where(DailyRecord.batch_id == batch.id).order_by(DailyRecord.day_index)).all()
    rows = snapshot(records)
    return batch, source, rows, fingerprint(batch, source, rows)


def find_artifact(session, batch, data_hash):
    return session.scalar(select(ForecastArtifact).where(ForecastArtifact.batch_id == batch.id,
        ForecastArtifact.fingerprint == data_hash, ForecastArtifact.config_key == CONFIG_KEY))


def prepare(session, batch_id):
    batch, source, rows, data_hash = load_data(session, batch_id)
    validate_dataset(batch, source, rows)
    existing = find_artifact(session, batch, data_hash)
    if existing:
        return existing
    report, predictor = evaluate(rows)
    model_id = f"ml02-{data_hash[:16]}-{CONFIG_KEY[:10]}"
    report.update(dataset_fingerprint=data_hash, raw_sha256=batch.sha256, model_id=model_id,
        source={key: getattr(source, key) for key in ("key", "title", "kind", "doi", "url", "authors", "license")})
    artifact = ForecastArtifact(batch_id=batch.id, fingerprint=data_hash, config_key=CONFIG_KEY,
        model_id=model_id, evaluation=report, predictor=predictor)
    session.add(artifact)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        artifact = find_artifact(session, batch, data_hash)
        if artifact is None:
            raise
    return artifact


def metadata(artifact):
    report = artifact.evaluation
    return {"model_id": artifact.model_id, "batch_id": artifact.batch_id, "dataset_fingerprint": artifact.fingerprint,
        "config_key": artifact.config_key, "version": VERSION, "selected_method": report["selected_method"],
        "selected_label": report["selected_label"], "created_at": artifact.created_at.replace(tzinfo=timezone.utc) if artifact.created_at.tzinfo is None else artifact.created_at,
        "quality_policy": report["quality_policy"], "production_training": report["production_training"],
        "evaluation_fit_cutoff": report["baseline_period"], "holdout_period": report["holdout_period"],
        "source": report["source"], "serialization": "JSON numeric state only; no pickle/joblib files"}


def require_artifact(session, batch_id):
    batch, source, rows, data_hash = load_data(session, batch_id)
    validate_dataset(batch, source, rows)
    artifact = find_artifact(session, batch, data_hash)
    if artifact is None:
        raise HTTPException(409, detail={"message": "No current artifact for this dataset/configuration. Evaluate & prepare this batch first."})
    return artifact


def preview_forecast(session, request):
    artifact = require_artifact(session, request.batch_id)
    state = artifact.predictor
    service_date = request.service_date.isoformat()
    if service_date <= state["last_observation_date"]:
        raise ForecastProblem(f"Service date must be after the last recorded date ({state['last_observation_date']}); historical outcomes cannot enter their own forecast.")
    predicted, unknown = predict_production(state, service_date, request.menu)
    mass = {key: predicted[key] * request.planned_diners / 1000 for key in ("plate", "kitchen")}
    mass["combined"] = mass["plate"] + mass["kitchen"]
    warnings = ["Forecast / Model estimate, not a measurement or savings claim.",
        "Kilogram estimates assume the planned diner count; actual future attendance is unknown.",
        "This is a next-observed-service forecast using the latest available history; no intervening future observations are assumed."]
    if unknown:
        warnings.append("Menu is missing or unseen in eligible training data. The recent 10-day mean fallback was used.")
    gap = (request.service_date - date.fromisoformat(state["last_observation_date"])).days
    if gap > 14:
        warnings.append(f"Historical data is {gap} calendar days older than this scenario. Long-gap forecasting reliability has not been validated.")
    result = {"label": "Forecast / Model estimate", "model_id": artifact.model_id, "method": state["method"],
        "effective_method": "recent_mean_10" if unknown else state["method"], "rates_g_per_diner": predicted,
        "estimated_mass_kg": mass, "warnings": warnings, "last_observation_date": state["last_observation_date"],
        "training_eligible_days": state["training"]["eligible"]}
    return result


def save_forecast(session, request):
    result = preview_forecast(session, request)
    artifact = require_artifact(session, request.batch_id)
    run = ForecastRun(artifact_id=artifact.id, batch_id=request.batch_id,
        scenario=request.model_dump(mode="json"), result=result)
    session.add(run)
    session.commit()
    return run


def run_info(run):
    result = {key: getattr(run, key) for key in ("id", "batch_id", "artifact_id", "created_at", "scenario", "result")}
    if result["created_at"].tzinfo is None:
        result["created_at"] = result["created_at"].replace(tzinfo=timezone.utc)
    return result


def forecast_router(factory):
    router = APIRouter(prefix="/api", tags=["Forecast Lab"])
    training_lock = threading.Lock()

    @router.get("/models/status", response_model=ModelStatus)
    def status(batch_id: int | None = Query(None, gt=0)):
        with factory() as session:
            if batch_id is None and session.scalar(select(ImportBatch.id).limit(1)) is None:
                return {"status": "empty", "batch_id": None, "reason": "Import a measured dataset to start."}
            batch, source, rows, data_hash = load_data(session, batch_id)
            try:
                validate_dataset(batch, source, rows)
            except ForecastProblem as exc:
                return {"status": "blocked", "batch_id": batch.id, "reason": str(exc)}
            artifact = find_artifact(session, batch, data_hash)
            return {"status": "ready" if artifact else "not_prepared", "batch_id": batch.id,
                "metadata": metadata(artifact) if artifact else None}

    @router.post("/models/train", response_model=ModelMetadata)
    def train(request: BatchRequest):
        with training_lock, factory() as session:
            return metadata(prepare(session, request.batch_id))

    @router.get("/models/metadata", response_model=ModelMetadata)
    def model_metadata(batch_id: int | None = Query(None, gt=0)):
        with factory() as session:
            return metadata(require_artifact(session, batch_id))

    @router.get("/models/evaluation", response_model=Evaluation)
    def evaluation(batch_id: int | None = Query(None, gt=0)):
        with factory() as session:
            return require_artifact(session, batch_id).evaluation

    @router.post("/forecasts", response_model=SavedForecast, status_code=201)
    def forecast(request: ForecastRequest):
        with factory() as session:
            return run_info(save_forecast(session, request))

    @router.post("/forecasts/preview", response_model=ForecastResult)
    def preview(request: ForecastRequest):
        with factory() as session:
            return preview_forecast(session, request)

    @router.get("/forecasts/runs", response_model=list[SavedForecast])
    def runs(batch_id: int = Query(gt=0), limit: int = Query(20, ge=1, le=100)):
        with factory() as session:
            load_data(session, batch_id)
            return [run_info(r) for r in session.scalars(select(ForecastRun).where(ForecastRun.batch_id == batch_id)
                .order_by(ForecastRun.id.desc()).limit(limit)).all()]

    return router
