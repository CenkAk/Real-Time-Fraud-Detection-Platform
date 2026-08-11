"""Leakage-safe online feature computation from prior transaction history."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from statistics import median
from typing import Protocol

from fraud_detection.domain import Transaction


class HistoryProvider(Protocol):
    def prior_transactions(self, transaction: Transaction, days: int) -> Sequence[Transaction]: ...


@dataclass(frozen=True)
class FeatureVector:
    """Named model inputs available at the exact time of authorization."""

    values: dict[str, float]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def calculate_features(
    transaction: Transaction,
    history: Sequence[Transaction],
    *,
    impossible_travel_kmh: float = 900.0,
) -> FeatureVector:
    """Calculate point-in-time features using only events older than the input event."""

    prior = sorted(
        (item for item in history if item.timestamp < transaction.timestamp),
        key=lambda item: item.timestamp,
    )
    amounts = [item.amount for item in prior]
    average = sum(amounts) / len(amounts) if amounts else transaction.amount
    med = median(amounts) if amounts else transaction.amount

    def recent(window: timedelta) -> list[Transaction]:
        boundary = transaction.timestamp - window
        return [item for item in prior if item.timestamp >= boundary]

    last_1m = recent(timedelta(minutes=1))
    last_5m = recent(timedelta(minutes=5))
    last_1h = recent(timedelta(hours=1))
    last_24h = recent(timedelta(hours=24))
    known_merchants = {item.merchant_id for item in prior}
    known_countries = {item.country for item in prior}
    known_devices = {item.device_id for item in prior}

    travel_speed = 0.0
    impossible_travel = 0.0
    if prior and transaction.latitude is not None and transaction.longitude is not None:
        previous = prior[-1]
        if previous.latitude is not None and previous.longitude is not None:
            hours = (transaction.timestamp - previous.timestamp).total_seconds() / 3600
            if hours > 0:
                travel_speed = (
                    _haversine_km(
                        previous.latitude,
                        previous.longitude,
                        transaction.latitude,
                        transaction.longitude,
                    )
                    / hours
                )
                impossible_travel = float(travel_speed > impossible_travel_kmh)

    return FeatureVector(
        {
            "amount": transaction.amount,
            "hour": float(transaction.timestamp.hour),
            "weekday": float(transaction.timestamp.weekday()),
            "user_average_amount": average,
            "user_median_amount": med,
            "amount_vs_user_average": transaction.amount / max(average, 0.01),
            "transactions_last_1m": float(len(last_1m)),
            "transactions_last_5m": float(len(last_5m)),
            "transactions_last_1h": float(len(last_1h)),
            "transactions_last_24h": float(len(last_24h)),
            "amount_last_1h": sum(item.amount for item in last_1h),
            "unique_merchants_last_24h": float(len({item.merchant_id for item in last_24h})),
            "unique_countries_last_24h": float(len({item.country for item in last_24h})),
            "new_merchant": float(bool(prior) and transaction.merchant_id not in known_merchants),
            "new_country": float(bool(prior) and transaction.country not in known_countries),
            "new_device": float(bool(prior) and transaction.device_id not in known_devices),
            "ip_changed": float(bool(prior) and transaction.ip_address != prior[-1].ip_address),
            "travel_speed_kmh": travel_speed,
            "impossible_travel": impossible_travel,
        }
    )


class InMemoryHistory:
    """Deterministic history provider used by tests and the local fallback."""

    def __init__(self) -> None:
        self._transactions: list[Transaction] = []

    def add(self, transaction: Transaction) -> None:
        if all(item.transaction_id != transaction.transaction_id for item in self._transactions):
            self._transactions.append(transaction)

    def prior_transactions(self, transaction: Transaction, days: int = 30) -> list[Transaction]:
        boundary = transaction.timestamp - timedelta(days=days)
        return [
            item
            for item in self._transactions
            if item.user_id == transaction.user_id
            and boundary <= item.timestamp < transaction.timestamp
            and item.transaction_id != transaction.transaction_id
        ]
