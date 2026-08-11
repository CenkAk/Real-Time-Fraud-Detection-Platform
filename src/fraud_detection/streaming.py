from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from fraud_detection.database import OutboxEventRecord

logger = logging.getLogger(__name__)


def build_producer(bootstrap_servers: str) -> Any:
    from confluent_kafka import Producer

    return Producer(
        {
            "bootstrap.servers": bootstrap_servers,
            "enable.idempotence": True,
            "acks": "all",
            "retries": 10,
            "client.id": "fraud-platform",
        }
    )


def publish_json(producer: Any, topic: str, key: str, payload: dict[str, object]) -> None:
    producer.produce(
        topic=topic,
        key=key.encode(),
        value=json.dumps(payload, separators=(",", ":"), default=str).encode(),
    )
    producer.poll(0)


def publish_outbox_batch(
    factory: sessionmaker[Session], producer: Any, batch_size: int = 100
) -> int:
    session = factory()
    try:
        rows = list(
            session.scalars(
                select(OutboxEventRecord)
                .where(OutboxEventRecord.published_at.is_(None))
                .order_by(OutboxEventRecord.created_at)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        )
        for row in rows:
            try:
                publish_json(producer, row.topic, row.event_key, row.payload)
                producer.flush(10)
                row.published_at = datetime.now(UTC)
                row.attempts += 1
                row.last_error = None
            except Exception as exc:
                row.attempts += 1
                row.last_error = str(exc)[:2000]
                logger.exception("outbox_publish_failed", extra={"event_id": row.event_id})
        session.commit()
        return sum(row.published_at is not None for row in rows)
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
