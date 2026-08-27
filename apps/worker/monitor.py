import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

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
from fraud_detection.lifecycle import (
    drift_threshold_breached,
    evaluate_delayed_performance,
    queue_retraining_job,
)
from fraud_detection.observability import configure_logging

logger = logging.getLogger(__name__)


def generate_report() -> bool:
    settings = get_settings()
    artifact = cast(dict[str, Any], joblib.load(settings.model_path))
    reference = cast(dict[str, Any], artifact["reference_distributions"])
    _, factory = create_session_factory(settings.database_url)
    session = factory()
    window_end = datetime.now(UTC)
    window_start = window_end - timedelta(days=1)
    try:
        rows = session.execute(
            select(
                TransactionRecord.amount,
                TransactionRecord.country,
                TransactionRecord.merchant_category,
                TransactionRecord.channel,
                PredictionRecord.fraud_probability,
                PredictionRecord.feature_snapshot,
            )
            .join(PredictionRecord)
            .where(TransactionRecord.timestamp >= window_start)
        ).all()
        if len(rows) < 100:
            return False
        velocity = [
            float((row.feature_snapshot or {}).get("transactions_last_1h", 0)) for row in rows
        ]
        metrics: dict[str, Any] = {
            "amount": numeric_drift(
                np.asarray(reference["amount"]), np.asarray([row.amount for row in rows])
            ),
            "fraud_probability": numeric_drift(
                np.asarray(reference["fraud_probability"]),
                np.asarray([row.fraud_probability for row in rows]),
            ),
            "country_js": categorical_drift(reference["country"], [row.country for row in rows]),
        }
        if "velocity" in reference:
            metrics["velocity"] = numeric_drift(
                np.asarray(reference["velocity"]), np.asarray(velocity)
            )
        for feature, values in {
            "merchant_category": [row.merchant_category for row in rows],
            "channel": [row.channel for row in rows],
        }.items():
            if feature in reference:
                metrics[f"{feature}_js"] = categorical_drift(reference[feature], values)

        reports = [("all", metrics)]
        for dimension in ("country", "merchant_category", "channel"):
            grouped: dict[str, list[Any]] = {}
            for row in rows:
                grouped.setdefault(str(getattr(row, dimension)), []).append(row)
            for value, segment_rows in grouped.items():
                if len(segment_rows) < 30:
                    continue
                reports.append(
                    (
                        f"{dimension}:{value}",
                        {
                            "sample_size": len(segment_rows),
                            "amount": numeric_drift(
                                np.asarray(reference["amount"]),
                                np.asarray([row.amount for row in segment_rows]),
                            ),
                            "fraud_probability": numeric_drift(
                                np.asarray(reference["fraud_probability"]),
                                np.asarray([row.fraud_probability for row in segment_rows]),
                            ),
                        },
                    )
                )

        detected = False
        for segment, report_metrics in reports:
            breached = drift_threshold_breached(report_metrics)
            previous = session.scalar(
                select(DriftReportRecord)
                .where(
                    DriftReportRecord.model_version == artifact["version"],
                    DriftReportRecord.segment == segment,
                )
                .order_by(DriftReportRecord.window_end.desc())
                .limit(1)
            )
            report = DriftReportRecord(
                model_version=artifact["version"],
                window_start=window_start,
                window_end=window_end,
                metrics=report_metrics,
                drift_detected=breached,
                segment=segment,
            )
            session.add(report)
            session.flush()
            if breached and previous is not None and previous.drift_detected:
                queue_retraining_job(
                    session,
                    trigger_type="DRIFT",
                    champion_version=artifact["version"],
                    metadata={
                        "segment": segment,
                        "current_report_id": report.report_id,
                        "previous_report_id": previous.report_id,
                    },
                )
                detected = True
        evaluate_delayed_performance(
            session,
            model_version=artifact["version"],
            champion_report_path=Path("artifacts/model_report.json"),
        )
        session.commit()
        logger.info(
            "drift_detected" if detected else "drift_checked",
            extra={"metrics": metrics, "segments": len(reports)},
        )
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
