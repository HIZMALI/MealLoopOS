"""Source provenance, immutable import batches and ordered daily measurements."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("source_datasets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(200), nullable=False, unique=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("doi", sa.String(100)), sa.Column("url", sa.String(500)),
        sa.Column("authors", sa.String(500)), sa.Column("license", sa.String(100)))
    op.create_table("import_batches",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source_id", sa.Integer, sa.ForeignKey("source_datasets.id"), nullable=False),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_count", sa.Integer, nullable=False),
        sa.Column("baseline_days", sa.Integer), sa.Column("inspection", sa.JSON, nullable=False),
        sa.UniqueConstraint("sha256", name="uq_import_sha256"))
    op.create_table("daily_records",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("batch_id", sa.Integer, sa.ForeignKey("import_batches.id"), nullable=False),
        sa.Column("day_index", sa.Integer, nullable=False), sa.Column("source_row", sa.Integer, nullable=False),
        sa.Column("date", sa.Date), sa.Column("phase", sa.String(20), nullable=False),
        sa.Column("menu", sa.Integer), sa.Column("diners", sa.Integer),
        sa.Column("plate_waste_kg", sa.Float), sa.Column("kitchen_serving_waste_kg", sa.Float),
        sa.Column("reported_plate_waste_g", sa.Float), sa.Column("reported_plate_g_per_diner", sa.Float),
        sa.Column("reported_kitchen_g_per_diner", sa.Float), sa.Column("issues", sa.JSON, nullable=False),
        sa.UniqueConstraint("batch_id", "day_index", name="uq_batch_day"),
        sa.CheckConstraint("diners IS NULL OR diners >= 0", name="ck_diners_nonnegative"),
        sa.CheckConstraint("plate_waste_kg IS NULL OR plate_waste_kg >= 0", name="ck_plate_nonnegative"),
        sa.CheckConstraint("kitchen_serving_waste_kg IS NULL OR kitchen_serving_waste_kg >= 0", name="ck_kitchen_nonnegative"))
    op.create_index("ix_daily_records_batch_id", "daily_records", ["batch_id"])


def downgrade():
    op.drop_table("daily_records")
    op.drop_table("import_batches")
    op.drop_table("source_datasets")
