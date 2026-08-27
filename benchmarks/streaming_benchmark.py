from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from uuid import uuid4

import numpy as np
from confluent_kafka import Consumer

from fraud_detection.streaming import build_producer, publish_json


def transaction(identifier: str) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "transaction_id": identifier,
        "user_id": f"benchmark-user-{identifier[-6:]}",
        "merchant_id": "benchmark-merchant",
        "timestamp": datetime.now(UTC).isoformat(),
        "amount": 99.95,
        "currency": "USD",
        "merchant_category": "grocery",
        "country": "US",
        "device_id": f"benchmark-device-{identifier[-6:]}",
        "ip_address": "192.0.2.30",
        "channel": "web",
    }


def percentile(samples: list[float], value: float) -> float:
    return float(np.percentile(np.asarray(samples), value)) if samples else 0.0


def run(rate: int, warmup_seconds: int, measure_seconds: int, bootstrap: str) -> dict[str, object]:
    producer = build_producer(bootstrap)
    group_id = f"stream-benchmark-{uuid4().hex}"
    consumer = Consumer(
        {
            "bootstrap.servers": bootstrap,
            "group.id": group_id,
            "auto.offset.reset": "latest",
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe(["fraud_predictions.v1"])
    consumer.poll(1.0)
    sent: dict[str, float] = {}
    measured_ids: set[str] = set()
    latencies_ms: list[float] = []
    start = time.perf_counter()
    measure_start = start + warmup_seconds
    finish_sending = measure_start + measure_seconds
    interval = 1 / rate
    next_send = start
    try:
        while time.perf_counter() < finish_sending:
            now = time.perf_counter()
            if now >= next_send:
                identifier = f"stream-benchmark-{uuid4().hex}"
                publish_json(producer, "transactions.v1", identifier, transaction(identifier))
                sent[identifier] = now
                if now >= measure_start:
                    measured_ids.add(identifier)
                next_send += interval
            message = consumer.poll(0)
            if message is not None and message.error() is None and message.key() is not None:
                identifier = message.key().decode()
                if identifier in measured_ids and identifier in sent:
                    latencies_ms.append((time.perf_counter() - sent.pop(identifier)) * 1000)
            if now < next_send:
                time.sleep(min(next_send - now, 0.002))
        producer.flush(30)
        drain_deadline = time.perf_counter() + 60
        while len(latencies_ms) < len(measured_ids) and time.perf_counter() < drain_deadline:
            message = consumer.poll(0.1)
            if message is None or message.error() is not None or message.key() is None:
                continue
            identifier = message.key().decode()
            if identifier in measured_ids and identifier in sent:
                latencies_ms.append((time.perf_counter() - sent.pop(identifier)) * 1000)
    finally:
        consumer.close()
        producer.flush(10)
    received = len(latencies_ms)
    expected = len(measured_ids)
    return {
        "rate_events_per_second": rate,
        "warmup_seconds": warmup_seconds,
        "measurement_seconds": measure_seconds,
        "sent": expected,
        "received": received,
        "delivery_ratio": received / expected if expected else 0,
        "throughput_events_per_second": received / measure_seconds,
        "latency_ms": {
            "average": mean(latencies_ms) if latencies_ms else 0,
            "p50": percentile(latencies_ms, 50),
            "p95": percentile(latencies_ms, 95),
            "p99": percentile(latencies_ms, 99),
            "maximum": max(latencies_ms, default=0),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rate", type=int, choices=[10, 50, 100], required=True)
    parser.add_argument("--warmup-seconds", type=int, default=120)
    parser.add_argument("--measure-seconds", type=int, default=300)
    parser.add_argument("--bootstrap", default="localhost:19092")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.rate, args.warmup_seconds, args.measure_seconds, args.bootstrap)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
