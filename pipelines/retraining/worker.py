from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from fraud_detection.config import get_settings
from fraud_detection.database import (
    ModelVersionRecord,
    RetrainingJobRecord,
    create_session_factory,
)
from fraud_detection.observability import configure_logging
from pipelines.retraining.run import compare_reports
from pipelines.training.train import train

logger = logging.getLogger(__name__)


def process_job(
    session: Session,
    job: RetrainingJobRecord,
    *,
    trainer: Callable[[Path, Path, Path, int], dict[str, object]] = train,
    trials: int = 20,
) -> None:
    job.status = "RUNNING"
    job.started_at = datetime.now(UTC)
    session.commit()
    artifact_path = Path(f"artifacts/models/challenger-{job.job_id}.joblib")
    report_path = Path(f"artifacts/retraining/{job.job_id}.json")
    try:
        challenger = trainer(
            Path("data/processed/features.parquet"), artifact_path, report_path, trials
        )
        champion = json.loads(Path("artifacts/model_report.json").read_text(encoding="utf-8"))
        decision = compare_reports(champion, challenger)
        registry_version = challenger.get("registered_model_version")
        if not isinstance(registry_version, str):
            raise RuntimeError("challenger was not registered in MLflow")
        job.status = "COMPLETED"
        job.challenger_version = registry_version
        job.promotion_recommended = bool(decision["promotion_recommended"])
        job.trigger_metadata = {
            **job.trigger_metadata,
            "gate_decision": decision,
            "challenger_model_version": challenger["model_version"],
            "report_path": str(report_path),
        }
        job.completed_at = datetime.now(UTC)
        test_metrics = cast(dict[str, object], challenger["test_metrics"])
        session.merge(
            ModelVersionRecord(
                version=str(challenger["model_version"]),
                stage="challenger",
                artifact_uri=str(artifact_path),
                metrics={
                    **test_metrics,
                    "expected_cost": challenger["test_expected_cost"],
                    "mlflow_version": registry_version,
                    "gate_decision": decision,
                },
            )
        )
        session.commit()
    except Exception as exc:
        session.rollback()
        refreshed = session.get(RetrainingJobRecord, job.job_id)
        assert refreshed is not None
        refreshed.status = "FAILED"
        refreshed.error = str(exc)
        refreshed.completed_at = datetime.now(UTC)
        session.commit()
        raise


def process_next(session: Session) -> bool:
    job = session.scalar(
        select(RetrainingJobRecord)
        .where(RetrainingJobRecord.status == "QUEUED")
        .order_by(RetrainingJobRecord.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if job is None:
        return False
    process_job(session, job)
    return True


def recover_interrupted_jobs(session: Session) -> int:
    jobs = session.scalars(
        select(RetrainingJobRecord).where(RetrainingJobRecord.status == "RUNNING")
    ).all()
    for job in jobs:
        previous_count = job.trigger_metadata.get("recovery_count", 0)
        recovery_count = (previous_count if isinstance(previous_count, int) else 0) + 1
        job.status = "QUEUED"
        job.started_at = None
        job.trigger_metadata = {**job.trigger_metadata, "recovery_count": recovery_count}
    session.commit()
    return len(jobs)


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    _, factory = create_session_factory(settings.database_url)
    recovery_session = factory()
    try:
        recovered = recover_interrupted_jobs(recovery_session)
        if recovered:
            logger.warning("retraining_jobs_recovered", extra={"count": recovered})
    finally:
        recovery_session.close()
    while True:
        session = factory()
        try:
            if not process_next(session):
                time.sleep(15)
        except Exception:
            logger.exception("retraining_job_failed")
        finally:
            session.close()


if __name__ == "__main__":
    run()
