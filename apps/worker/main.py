import logging
import signal
import threading
import time
from datetime import UTC, datetime
from typing import Any

from prometheus_client import start_http_server
from sqlalchemy import func, select

from fraud_detection.config import get_settings
from fraud_detection.database import (
    OutboxEventRecord,
    create_session_factory,
    score_and_persist,
)
from fraud_detection.decision import DecisionEngine
from fraud_detection.domain import Transaction
from fraud_detection.model import load_model
from fraud_detection.observability import (
    CONSUMER_LAG,
    DLQ_EVENTS,
    ERRORS,
    EVENT_LATENCY,
    OUTBOX_OLDEST_AGE,
    OUTBOX_PENDING,
    REQUEST_ID,
    TRANSACTIONS,
    WORKER_EVENTS,
    configure_logging,
)
from fraud_detection.streaming import build_producer, publish_json, publish_outbox_batch

logger = logging.getLogger(__name__)
running = True


def stop(*_: object) -> None:
    global running
    running = False


def outbox_loop(factory: Any, producer: Any) -> None:
    while running:
        published = publish_outbox_batch(factory, producer)
        with factory() as session:
            pending, oldest = session.execute(
                select(func.count(), func.min(OutboxEventRecord.created_at)).where(
                    OutboxEventRecord.published_at.is_(None)
                )
            ).one()
            OUTBOX_PENDING.set(pending)
            if oldest is None:
                OUTBOX_OLDEST_AGE.set(0)
            else:
                if oldest.tzinfo is None:
                    oldest = oldest.replace(tzinfo=UTC)
                OUTBOX_OLDEST_AGE.set(max((datetime.now(UTC) - oldest).total_seconds(), 0))
        if published == 0:
            time.sleep(0.5)


def run() -> None:
    from confluent_kafka import Consumer, KafkaError, TopicPartition

    settings = get_settings()
    configure_logging(settings.log_level)
    start_http_server(9101)
    _, factory = create_session_factory(settings.database_url)
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
            error = message.error()
            if error is not None:
                if error.code() != KafkaError._PARTITION_EOF:
                    logger.error("consumer_error", extra={"error": str(error)})
                continue
            raw_value = message.value()
            request_token = None
            try:
                if raw_value is None:
                    raise ValueError("Kafka message payload is empty")
                transaction = Transaction.model_validate_json(raw_value)
                request_token = REQUEST_ID.set(str(transaction.request_id))
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
                WORKER_EVENTS.labels("processed").inc()
                EVENT_LATENCY.observe(
                    max((datetime.now(UTC) - transaction.timestamp).total_seconds(), 0)
                )
                topic = message.topic()
                partition = message.partition()
                offset = message.offset()
                if topic is None or partition is None or offset is None:
                    raise ValueError("Kafka message metadata is incomplete")
                _, high = consumer.get_watermark_offsets(
                    TopicPartition(topic, partition), cached=False
                )
                CONSUMER_LAG.labels(
                    "fraud-scorers-v1", topic, str(partition)
                ).set(max(high - offset - 1, 0))
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
                WORKER_EVENTS.labels("failed").inc()
                DLQ_EVENTS.inc()
                logger.exception("prediction_error")
                raw_key = message.key()
                publish_json(
                    producer,
                    "transactions.dlq.v1",
                    raw_key.decode() if raw_key else "unknown",
                    {
                        "original_payload": (
                            raw_value.decode(errors="replace") if raw_value else ""
                        ),
                        "error": str(exc),
                    },
                )
                producer.flush(10)
                consumer.commit(message=message, asynchronous=False)
            finally:
                if request_token is not None:
                    REQUEST_ID.reset(request_token)
    finally:
        consumer.close()
        producer.flush(10)


if __name__ == "__main__":
    run()
