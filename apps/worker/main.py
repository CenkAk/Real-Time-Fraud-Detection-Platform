"""Redpanda transaction consumer and outbox publisher."""

import logging
import signal
import threading
import time
from typing import Any

from prometheus_client import start_http_server

from fraud_detection.config import get_settings
from fraud_detection.database import Base, create_session_factory, score_and_persist
from fraud_detection.decision import DecisionEngine
from fraud_detection.domain import Transaction
from fraud_detection.model import load_model
from fraud_detection.observability import ERRORS, TRANSACTIONS, configure_logging
from fraud_detection.streaming import build_producer, publish_json, publish_outbox_batch

logger = logging.getLogger(__name__)
running = True


def stop(*_: object) -> None:
    global running
    running = False


def outbox_loop(factory: Any, producer: Any) -> None:
    while running:
        published = publish_outbox_batch(factory, producer)
        if published == 0:
            time.sleep(0.5)


def run() -> None:
    from confluent_kafka import Consumer, KafkaError

    settings = get_settings()
    configure_logging(settings.log_level)
    start_http_server(9101)
    engine, factory = create_session_factory(settings.database_url)
    Base.metadata.create_all(engine)
    model = load_model(settings.model_path)
    decisions = DecisionEngine(
        review_threshold=(
            model.review_threshold
            if settings.use_model_thresholds
            else settings.fraud_review_threshold
        ),
        block_threshold=(
            model.block_threshold
            if settings.use_model_thresholds
            else settings.fraud_block_threshold
        ),
    )
    producer = build_producer(settings.kafka_bootstrap_servers)
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": "fraud-scorers-v1",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe(["transactions.v1"])
    publisher = threading.Thread(target=outbox_loop, args=(factory, producer), daemon=True)
    publisher.start()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logger.info("model_loaded", extra={"model_version": model.version})

    try:
        while running:
            message = consumer.poll(1.0)
            if message is None:
                continue
            if message.error():
                if message.error().code() != KafkaError._PARTITION_EOF:
                    logger.error("consumer_error", extra={"error": str(message.error())})
                continue
            try:
                transaction = Transaction.model_validate_json(message.value())
                session = factory()
                try:
                    prediction = score_and_persist(session, transaction, model, decisions)
                    session.commit()
                except Exception:
                    session.rollback()
                    raise
                finally:
                    session.close()
                consumer.commit(message=message, asynchronous=False)
                TRANSACTIONS.labels(prediction.decision.value).inc()
                logger.info(
                    "prediction_completed",
                    extra={
                        "transaction_id": transaction.transaction_id,
                        "decision": prediction.decision.value,
                        "model_version": prediction.model_version,
                    },
                )
            except Exception as exc:
                ERRORS.labels("consumer", type(exc).__name__).inc()
                logger.exception("prediction_error")
                publish_json(
                    producer,
                    "transactions.dlq.v1",
                    message.key().decode() if message.key() else "unknown",
                    {
                        "original_payload": message.value().decode(errors="replace"),
                        "error": str(exc),
                    },
                )
                producer.flush(10)
                consumer.commit(message=message, asynchronous=False)
    finally:
        consumer.close()
        producer.flush(10)


if __name__ == "__main__":
    run()
