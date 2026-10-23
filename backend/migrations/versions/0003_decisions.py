"""Immutable assumption-based planning snapshots, separate from measured data."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("decision_plans",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("engine_version", sa.String(40), nullable=False),
        sa.Column("evidence_type", sa.String(30), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("inputs", sa.JSON, nullable=False), sa.Column("result", sa.JSON, nullable=False),
        sa.Column("context_reference", sa.JSON),
        sa.CheckConstraint("evidence_type = 'assumption_based'", name="ck_decision_evidence"))
    op.create_index("ix_decision_plans_input_fingerprint", "decision_plans", ["input_fingerprint"])


def downgrade():
    op.drop_table("decision_plans")
