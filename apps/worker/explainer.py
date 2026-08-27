import logging
import signal

import joblib
from prometheus_client import start_http_server
from sqlalchemy import select

from fraud_detection.config import get_settings
from fraud_detection.database import (
    FraudAlertRecord,
    PredictionRecord,
    SQLHistoryProvider,
    TransactionRecord,
    create_session_factory,
    transaction_from_record,
)
from fraud_detection.explainability import reason_code_explanation, shap_explanation
from fraud_detection.features import calculate_features
from fraud_detection.observability import configure_logging

logger = logging.getLogger(__name__)
running = True


def stop(*_: object) -> None:
    global running
    running = False


def run() -> None:
    from confluent_kafka import Consumer

    settings = get_settings()
    configure_logging(settings.log_level)
    start_http_server(9102)
    _, factory = create_session_factory(settings.database_url)
    try:
        artifact = joblib.load(settings.model_path)
    except FileNotFoundError:
        artifact = None
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": "fraud-explainers-v1",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe(["fraud_alerts.v1"])
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        while running:
            message = consumer.poll(1)
            if message is None or message.error():
                continue
            raw_key = message.key()
            if raw_key is None:
                logger.error("explanation_message_missing_key")
                consumer.commit(message=message, asynchronous=False)
                continue
            transaction_id = raw_key.decode()
            session = factory()
            try:
                transaction_row = session.get(TransactionRecord, transaction_id)
                alert = session.scalar(
                    select(FraudAlertRecord).where(
                        FraudAlertRecord.transaction_id == transaction_id
                    )
                )
                if transaction_row is None or alert is None:
                    raise LookupError(transaction_id)
                prediction_row = session.get(PredictionRecord, transaction_id)
                if prediction_row is not None and prediction_row.feature_snapshot is not None:
                    features = prediction_row.feature_snapshot
                else:
                    transaction = transaction_from_record(transaction_row)
                    features = calculate_features(
                        transaction,
                        SQLHistoryProvider(session).prior_transactions(transaction, 30),
                    ).values
                factors = (
                    shap_explanation(artifact, features)
                    if artifact is not None and "background" in artifact
                    else reason_code_explanation(features)
                )
                alert.explanation = {
                    "method": "shap" if artifact is not None else "reason_codes",
                    "top_risk_factors": [factor.model_dump() for factor in factors],
                }
                session.commit()
                consumer.commit(message=message, asynchronous=False)
                logger.info("explanation_completed", extra={"transaction_id": transaction_id})
            except Exception:
                session.rollback()
                logger.exception("explanation_error", extra={"transaction_id": transaction_id})
            finally:
                session.close()
    finally:
        consumer.close()


if __name__ == "__main__":
    run()
