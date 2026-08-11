"""Scheduled data/prediction drift reports persisted for audit and retraining decisions."""

import logging
import time
from datetime import UTC, datetime, timedelta

import joblib
import numpy as np
from sqlalchemy import select

from fraud_detection.config import get_settings
from fraud_detection.database import (
    DriftReportRecord,
    PredictionRecord,
    TransactionRecord,
    create_session_factory,
)
from fraud_detection.drift import categorical_drift, numeric_drift
from fraud_detection.observability import configure_logging

logger = logging.getLogger(__name__)


def generate_report() -> bool:
    settings = get_settings()
    artifact = joblib.load(settings.model_path)
    reference = artifact["reference_distributions"]
    _, factory = create_session_factory(settings.database_url)
    session = factory()
    window_end = datetime.now(UTC)
    window_start = window_end - timedelta(days=1)
    try:
        rows = session.execute(
            select(
                TransactionRecord.amount,
                TransactionRecord.country,
                PredictionRecord.fraud_probability,
            )
            .join(PredictionRecord)
            .where(TransactionRecord.timestamp >= window_start)
        ).all()
        if len(rows) < 100:
            return False
        metrics = {
            "amount": numeric_drift(
                np.asarray(reference["amount"]), np.asarray([row.amount for row in rows])
            ),
            "fraud_probability": numeric_drift(
                np.asarray(reference["fraud_probability"]),
                np.asarray([row.fraud_probability for row in rows]),
            ),
            "country_js": categorical_drift(reference["country"], [row.country for row in rows]),
        }
        detected = (
            metrics["amount"]["psi"] >= 0.20
            or metrics["fraud_probability"]["psi"] >= 0.20
            or metrics["country_js"] >= 0.10
        )
        session.add(
            DriftReportRecord(
                model_version=artifact["version"],
                window_start=window_start,
                window_end=window_end,
                metrics=metrics,
                drift_detected=detected,
            )
        )
        session.commit()
        logger.info("drift_detected" if detected else "drift_checked", extra={"metrics": metrics})
        return detected
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run() -> None:
    configure_logging(get_settings().log_level)
    while True:
        try:
            generate_report()
        except Exception:
            logger.exception("drift_monitor_error")
        time.sleep(300)


if __name__ == "__main__":
    run()
