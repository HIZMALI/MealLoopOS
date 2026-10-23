from datetime import date as DateValue, datetime, timezone

from sqlalchemy import JSON, CheckConstraint, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class SourceDataset(Base):
    __tablename__ = "source_datasets"
    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(200), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(20))
    doi: Mapped[str | None] = mapped_column(String(100))
    url: Mapped[str | None] = mapped_column(String(500))
    authors: Mapped[str | None] = mapped_column(String(500))
    license: Mapped[str | None] = mapped_column(String(100))


class ImportBatch(Base):
    __tablename__ = "import_batches"
    __table_args__ = (UniqueConstraint("sha256", name="uq_import_sha256"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source_datasets.id"))
    filename: Mapped[str] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    row_count: Mapped[int] = mapped_column(Integer)
    baseline_days: Mapped[int | None] = mapped_column(Integer)
    inspection: Mapped[dict] = mapped_column(JSON)


class DailyRecord(Base):
    __tablename__ = "daily_records"
    __table_args__ = (
        UniqueConstraint("batch_id", "day_index", name="uq_batch_day"),
        CheckConstraint("diners IS NULL OR diners >= 0", name="ck_diners_nonnegative"),
        CheckConstraint("plate_waste_kg IS NULL OR plate_waste_kg >= 0", name="ck_plate_nonnegative"),
        CheckConstraint("kitchen_serving_waste_kg IS NULL OR kitchen_serving_waste_kg >= 0", name="ck_kitchen_nonnegative"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    day_index: Mapped[int] = mapped_column(Integer)
    source_row: Mapped[int] = mapped_column(Integer)
    date: Mapped[DateValue | None] = mapped_column(Date)
    phase: Mapped[str] = mapped_column(String(20))
    menu: Mapped[int | None] = mapped_column(Integer)
    diners: Mapped[int | None] = mapped_column(Integer)
    plate_waste_kg: Mapped[float | None] = mapped_column(Float)
    kitchen_serving_waste_kg: Mapped[float | None] = mapped_column(Float)
    reported_plate_waste_g: Mapped[float | None] = mapped_column(Float)
    reported_plate_g_per_diner: Mapped[float | None] = mapped_column(Float)
    reported_kitchen_g_per_diner: Mapped[float | None] = mapped_column(Float)
    issues: Mapped[list] = mapped_column(JSON)


class ForecastArtifact(Base):
    __tablename__ = "forecast_artifacts"
    __table_args__ = (UniqueConstraint("batch_id", "fingerprint", "config_key", name="uq_forecast_artifact"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    config_key: Mapped[str] = mapped_column(String(64))
    model_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    evaluation: Mapped[dict] = mapped_column(JSON)
    predictor: Mapped[dict] = mapped_column(JSON)


class ForecastRun(Base):
    __tablename__ = "forecast_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("forecast_artifacts.id"), index=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    scenario: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)


class DecisionPlan(Base):
    __tablename__ = "decision_plans"
    __table_args__ = (CheckConstraint("evidence_type = 'assumption_based'", name="ck_decision_evidence"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    engine_version: Mapped[str] = mapped_column(String(40))
    evidence_type: Mapped[str] = mapped_column(String(30), default="assumption_based")
    input_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    inputs: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    context_reference: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class OperationalService(Base):
    __tablename__ = "operational_services"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    demo_key: Mapped[str | None] = mapped_column(String(60), unique=True, nullable=True)


class OperationalRevision(Base):
    __tablename__ = "operational_revisions"
    __table_args__ = (UniqueConstraint("service_id", "version", name="uq_operational_service_version"),
        CheckConstraint("version >= 1", name="ck_operational_version"),
        CheckConstraint("status IN ('draft','finalized')", name="ck_operational_status"),
        CheckConstraint("source_category IN ('synthetic','user_reported','user_reported_documented')", name="ck_operational_source"))
    id: Mapped[int] = mapped_column(primary_key=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("operational_services.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    previous_revision_id: Mapped[int | None] = mapped_column(ForeignKey("operational_revisions.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    event: Mapped[str] = mapped_column(String(30))
    correction_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    changed_fields: Mapped[list] = mapped_column(JSON)
    source_category: Mapped[str] = mapped_column(String(40), index=True)
    service_date: Mapped[DateValue] = mapped_column(Date)
    decision_plan_id: Mapped[int | None] = mapped_column(ForeignKey("decision_plans.id"), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON)
    assessment: Mapped[dict] = mapped_column(JSON)
    plan_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
