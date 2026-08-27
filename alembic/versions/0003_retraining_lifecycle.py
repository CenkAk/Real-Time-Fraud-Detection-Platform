from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "drift_reports",
        sa.Column("segment", sa.String(length=128), nullable=False, server_default="all"),
    )
    op.create_table(
        "performance_reports",
        sa.Column("report_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("label_count", sa.Integer(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("degradation_detected", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("report_id"),
    )
    op.create_table(
        "retraining_jobs",
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("trigger_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("trigger_metadata", sa.JSON(), nullable=False),
        sa.Column("champion_version", sa.String(length=128), nullable=False),
        sa.Column("challenger_version", sa.String(length=128), nullable=True),
        sa.Column("promotion_recommended", sa.Boolean(), nullable=True),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("job_id"),
    )
    op.create_table(
        "model_promotions",
        sa.Column("promotion_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("previous_champion", sa.String(length=128), nullable=False),
        sa.Column("promoted_version", sa.String(length=128), nullable=False),
        sa.Column("promoted_by", sa.String(length=128), nullable=False),
        sa.Column("gate_results", sa.JSON(), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["retraining_jobs.job_id"]),
        sa.PrimaryKeyConstraint("promotion_id"),
    )


def downgrade() -> None:
    op.drop_table("model_promotions")
    op.drop_table("retraining_jobs")
    op.drop_table("performance_reports")
    op.drop_column("drift_reports", "segment")
