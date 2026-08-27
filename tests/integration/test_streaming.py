from __future__ import annotations

import json
from uuid import uuid4

import pytest

from fraud_detection.streaming import build_producer, publish_json

pytestmark = pytest.mark.integration


def test_redpanda_publish_and_manual_consume(kafka_bootstrap_servers: str) -> None:
    from confluent_kafka import Consumer

    topic = f"contract-test-{uuid4().hex}"
    producer = build_producer(kafka_bootstrap_servers)
    payload = {"schema_version": 1, "transaction_id": "integration-stream"}
    publish_json(producer, topic, "integration-stream", payload)
    assert producer.flush(10) == 0

    consumer = Consumer(
        {
            "bootstrap.servers": kafka_bootstrap_servers,
            "group.id": f"integration-{uuid4().hex}",
            "auto.offset.reset": "earliest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([topic])
    try:
        message = consumer.poll(10)
        assert message is not None and message.error() is None
        assert json.loads(message.value()) == payload
        consumer.commit(message=message, asynchronous=False)
    finally:
        consumer.close()
