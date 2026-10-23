"""Versioned JSON forecasting artifacts, frozen evaluations, and scenario runs."""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("forecast_artifacts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("batch_id", sa.Integer, sa.ForeignKey("import_batches.id"), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("config_key", sa.String(64), nullable=False),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluation", sa.JSON, nullable=False),
        sa.Column("predictor", sa.JSON, nullable=False),
        sa.UniqueConstraint("batch_id", "fingerprint", "config_key", name="uq_forecast_artifact"))
    op.create_index("ix_forecast_artifacts_batch_id", "forecast_artifacts", ["batch_id"])
    op.create_table("forecast_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("artifact_id", sa.Integer, sa.ForeignKey("forecast_artifacts.id"), nullable=False),
        sa.Column("batch_id", sa.Integer, sa.ForeignKey("import_batches.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scenario", sa.JSON, nullable=False), sa.Column("result", sa.JSON, nullable=False))
    op.create_index("ix_forecast_runs_artifact_id", "forecast_runs", ["artifact_id"])
    op.create_index("ix_forecast_runs_batch_id", "forecast_runs", ["batch_id"])


def downgrade():
    op.drop_table("forecast_runs")
    op.drop_table("forecast_artifacts")
