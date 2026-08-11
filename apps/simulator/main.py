"""Deterministic live transaction generator with explicit fraud scenarios."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from ipaddress import IPv4Address
from uuid import uuid4

from fraud_detection.config import get_settings
from fraud_detection.domain import Transaction
from fraud_detection.observability import configure_logging
from fraud_detection.streaming import build_producer, publish_json

COUNTRIES = [("US", 40.7128, -74.0060), ("GB", 51.5072, -0.1276), ("TR", 41.0082, 28.9784)]
CATEGORIES = ["grocery", "travel", "electronics", "fuel", "restaurant"]


@dataclass
class UserProfile:
    user_id: str
    country: str
    latitude: float
    longitude: float
    usual_device: str
    average_amount: float


class TransactionSimulator:
    def __init__(self, seed: int = 42, users: int = 100) -> None:
        self.random = random.Random(seed)
        self.sequence = 0
        self.users = []
        for index in range(users):
            country, latitude, longitude = self.random.choice(COUNTRIES)
            self.users.append(
                UserProfile(
                    user_id=f"user-{index:05d}",
                    country=country,
                    latitude=latitude,
                    longitude=longitude,
                    usual_device=f"device-{index:05d}",
                    average_amount=self.random.uniform(15, 200),
                )
            )

    def next(self) -> tuple[Transaction, bool]:
        self.sequence += 1
        user = self.random.choice(self.users)
        fraud = self.random.random() < 0.01
        country, latitude, longitude = (
            self.random.choice([item for item in COUNTRIES if item[0] != user.country])
            if fraud
            else (user.country, user.latitude, user.longitude)
        )
        amount = max(1, self.random.lognormvariate(0, 0.45) * user.average_amount)
        device = user.usual_device
        if fraud:
            amount *= self.random.uniform(4, 12)
            device = f"device-takeover-{self.random.randint(1, 10000)}"
        event = Transaction(
            transaction_id=f"txn-{datetime.now(UTC):%Y%m%d%H%M%S}-{self.sequence}-{uuid4().hex[:6]}",
            user_id=user.user_id,
            merchant_id=f"merchant-{self.random.randint(1, 500):05d}",
            timestamp=datetime.now(UTC),
            amount=round(amount, 2),
            currency="USD",
            merchant_category=self.random.choice(CATEGORIES),
            country=country,
            device_id=device,
            ip_address=IPv4Address(f"192.0.2.{self.random.randint(1, 254)}"),
            channel=self.random.choice(["web", "mobile", "pos"]),
            latitude=latitude,
            longitude=longitude,
        )
        return event, fraud


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    simulator = TransactionSimulator(settings.simulator_seed)
    producer = build_producer(settings.kafka_bootstrap_servers)
    delay = 1 / settings.simulator_rate_per_second
    while True:
        transaction, _hidden_label = simulator.next()
        publish_json(
            producer,
            "transactions.v1",
            transaction.transaction_id,
            transaction.model_dump(mode="json"),
        )
        producer.flush(10)
        time.sleep(delay)


if __name__ == "__main__":
    run()
