from datetime import date as DateValue, datetime
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BatchRequest(StrictModel):
    batch_id: Annotated[int, Field(strict=True, gt=0)]


class ForecastRequest(BatchRequest):
    service_date: DateValue
    planned_diners: Annotated[int, Field(strict=True, ge=1, le=1_000_000)]
    menu: Annotated[int | None, Field(strict=True, ge=1, le=10_000)] = None


class Rates(BaseModel):
    plate: float
    kitchen: float
    combined: float


class Errors(BaseModel):
    mae: float
    rmse: float


class Scores(BaseModel):
    n: int
    plate: Errors
    kitchen: Errors
    combined: Errors


class Exclusion(BaseModel):
    day_index: int
    source_row: int
    date: str
    reasons: list[str]


class Period(BaseModel):
    first_day: int
    last_day: int
    start_date: str
    end_date: str
    total: int
    eligible: int
    excluded: int
    exclusions: list[Exclusion]
    reason_counts: dict[str, int]


class Prediction(BaseModel):
    day_index: int
    source_row: int
    date: str
    included: bool
    exclusions: list[str]
    actual: Rates | None
    predictions: dict[str, Rates]
    history_last_day: int
    fit_cutoff_day: int


class Fold(BaseModel):
    training: Period
    validation: Period
    ridge_fit_audit: dict
    metrics: dict[str, Scores]


class Evaluation(BaseModel):
    version: str
    quality_policy: str
    configuration: dict
    selected_method: str
    selected_label: str
    method_labels: dict[str, str]
    selection_rule: str
    baseline_period: Period
    holdout_period: Period
    production_training: Period
    folds: list[Fold]
    validation_metrics: dict[str, Scores]
    holdout_metrics: dict[str, Scores]
    validation_predictions: list[Prediction]
    holdout_predictions: list[Prediction]
    holdout_fit_audit: dict
    limitations: list[str]
    dataset_fingerprint: str
    raw_sha256: str
    source: dict
    model_id: str


class ModelMetadata(BaseModel):
    model_id: str
    batch_id: int
    dataset_fingerprint: str
    config_key: str
    version: str
    selected_method: str
    selected_label: str
    created_at: datetime
    quality_policy: str
    production_training: Period
    evaluation_fit_cutoff: Period
    holdout_period: Period
    source: dict
    serialization: str


class ModelStatus(BaseModel):
    status: Literal["empty", "blocked", "not_prepared", "ready"]
    batch_id: int | None
    reason: str | None = None
    metadata: ModelMetadata | None = None


class ForecastResult(BaseModel):
    label: str
    model_id: str
    method: str
    effective_method: str
    rates_g_per_diner: Rates
    estimated_mass_kg: Rates
    warnings: list[str]
    last_observation_date: str
    training_eligible_days: int


class SavedForecast(BaseModel):
    id: int
    batch_id: int
    artifact_id: int
    created_at: datetime
    scenario: ForecastRequest
    result: ForecastResult
