from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address

from fraud_detection.domain import Transaction
from fraud_detection.features import calculate_features


def transaction(identifier: str, timestamp: datetime, **updates: object) -> Transaction:
    values: dict[str, object] = {
        "transaction_id": identifier,
        "user_id": "user-1",
        "merchant_id": "merchant-1",
        "timestamp": timestamp,
        "amount": 100.0,
        "currency": "USD",
        "merchant_category": "grocery",
        "country": "US",
        "device_id": "device-1",
        "ip_address": IPv4Address("192.0.2.1"),
        "channel": "web",
        "latitude": 40.7128,
        "longitude": -74.0060,
    }
    values.update(updates)
    return Transaction.model_validate(values)


def test_velocity_and_new_entity_features_use_only_prior_events() -> None:
    now = datetime(2026, 8, 10, 18, tzinfo=UTC)
    prior = transaction("old", now - timedelta(minutes=2))
    future = transaction("future", now + timedelta(minutes=1), amount=9999.0)
    current = transaction(
        "current",
        now,
        merchant_id="merchant-2",
        device_id="device-2",
        amount=200.0,
    )
    features = calculate_features(current, [future, prior]).values
    assert features["transactions_last_5m"] == 1
    assert features["user_average_amount"] == 100.0
    assert features["new_merchant"] == 1
    assert features["new_device"] == 1
