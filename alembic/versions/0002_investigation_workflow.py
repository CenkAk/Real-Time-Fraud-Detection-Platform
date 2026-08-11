from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    prediction_columns = {column["name"] for column in inspector.get_columns("predictions")}
    alert_columns = {column["name"] for column in inspector.get_columns("fraud_alerts")}
    if "feature_snapshot" not in prediction_columns:
        op.add_column("predictions", sa.Column("feature_snapshot", sa.JSON(), nullable=True))
    if "analyst_note" not in alert_columns:
        op.add_column("fraud_alerts", sa.Column("analyst_note", sa.Text(), nullable=True))
    if "resolution" not in alert_columns:
        op.add_column(
            "fraud_alerts",
            sa.Column("resolution", sa.String(length=16), nullable=True),
        )
    if "resolved_at" not in alert_columns:
        op.add_column(
            "fraud_alerts",
            sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("fraud_alerts", "resolved_at")
    op.drop_column("fraud_alerts", "resolution")
    op.drop_column("fraud_alerts", "analyst_note")
    op.drop_column("predictions", "feature_snapshot")
