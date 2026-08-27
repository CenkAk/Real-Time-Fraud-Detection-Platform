from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from mlflow.tracking import MlflowClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fraud_detection.database import (
    ModelPromotionRecord,
    ModelVersionRecord,
    RetrainingJobRecord,
)


def promote_completed_job(
    session: Session,
    job: RetrainingJobRecord,
    *,
    tracking_uri: str,
    requested_by: str,
    model_name: str = "fraud-detector",
) -> ModelPromotionRecord:
    existing = session.scalar(
        select(ModelPromotionRecord).where(ModelPromotionRecord.job_id == job.job_id)
    )
    if existing is not None:
        if job.status != "PROMOTED":
            job.status = "PROMOTED"
            session.commit()
        return existing
    if job.status != "COMPLETED" or not job.promotion_recommended:
        raise ValueError("challenger has not passed all promotion gates")
    if job.challenger_version is None:
        raise ValueError("challenger MLflow version is missing")
    client = MlflowClient(tracking_uri=tracking_uri)
    registered = client.get_registered_model(model_name)
    previous = registered.aliases.get("champion")
    if previous is None:
        raise ValueError("champion alias is missing")
    client.set_registered_model_alias(model_name, "champion", job.challenger_version)
    try:
        now = datetime.now(UTC)
        for record in session.query(ModelVersionRecord).filter_by(stage="champion"):
            record.stage = "archived"
        candidate_app_version = str(job.trigger_metadata["challenger_model_version"])
        candidate = session.get(ModelVersionRecord, candidate_app_version)
        if candidate is None:
            raise ValueError("challenger database version is missing")
        candidate.stage = "champion"
        candidate.promoted_at = now
        gate_results = cast(dict[str, object], job.trigger_metadata.get("gate_decision", {}))
        promotion = ModelPromotionRecord(
            job_id=job.job_id,
            previous_champion=previous,
            promoted_version=job.challenger_version,
            promoted_by=requested_by,
            gate_results=gate_results,
            promoted_at=now,
        )
        job.status = "PROMOTED"
        session.add(promotion)
        session.commit()
        return promotion
    except Exception:
        session.rollback()
        client.set_registered_model_alias(model_name, "champion", previous)
        raise
