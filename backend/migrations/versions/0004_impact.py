"""Append-only operational services and evidence revisions."""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("operational_services", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("demo_key", sa.String(60), nullable=True, unique=True))
    op.create_table("operational_revisions", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("service_id", sa.Integer, sa.ForeignKey("operational_services.id"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("previous_revision_id", sa.Integer, sa.ForeignKey("operational_revisions.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(20), nullable=False), sa.Column("event", sa.String(30), nullable=False),
        sa.Column("correction_reason", sa.String(1000), nullable=True),
        sa.Column("changed_fields", sa.JSON, nullable=False),
        sa.Column("source_category", sa.String(40), nullable=False), sa.Column("service_date", sa.Date, nullable=False),
        sa.Column("decision_plan_id", sa.Integer, sa.ForeignKey("decision_plans.id"), nullable=True),
        sa.Column("payload", sa.JSON, nullable=False), sa.Column("assessment", sa.JSON, nullable=False),
        sa.Column("plan_snapshot", sa.JSON, nullable=True),
        sa.UniqueConstraint("service_id", "version", name="uq_operational_service_version"),
        sa.CheckConstraint("version >= 1", name="ck_operational_version"),
        sa.CheckConstraint("status IN ('draft','finalized')", name="ck_operational_status"),
        sa.CheckConstraint("source_category IN ('synthetic','user_reported','user_reported_documented')", name="ck_operational_source"))
    for column in ("service_id", "source_category"):
        op.create_index(f"ix_operational_revisions_{column}", "operational_revisions", [column])


def downgrade():
    op.drop_table("operational_revisions")
    op.drop_table("operational_services")
