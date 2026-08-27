"""Make model promotion idempotent per retraining job.

Revision ID: 0004_promotion_idempotency
Revises: 0003
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004_promotion_idempotency"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE retraining_jobs
        SET status = 'PROMOTED'
        WHERE EXISTS (
            SELECT 1 FROM model_promotions
            WHERE model_promotions.job_id = retraining_jobs.job_id
        )
        """
    )
    op.create_unique_constraint(
        "uq_model_promotions_job_id", "model_promotions", ["job_id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_model_promotions_job_id", "model_promotions", type_="unique"
    )
