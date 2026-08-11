import os
from datetime import UTC, datetime

from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

from apps.api.main import app  # noqa: E402


def payload(identifier: str) -> dict[str, object]:
    return {
        "transaction_id": identifier,
        "user_id": "user-api",
        "merchant_id": "merchant-api",
        "timestamp": datetime.now(UTC).isoformat(),
        "amount": 149.95,
        "currency": "USD",
        "merchant_category": "electronics",
        "country": "US",
        "device_id": "device-api",
        "ip_address": "192.0.2.10",
        "channel": "web",
    }


def test_transaction_is_scored_and_idempotent() -> None:
    with TestClient(app) as client:
        first = client.post("/transactions", json=payload("txn-api-test"))
        second = client.post("/transactions", json=payload("txn-api-test"))
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["transaction_id"] == "txn-api-test"
    assert first.json()["fraud_probability"] == second.json()["fraud_probability"]


def test_naive_timestamp_is_rejected() -> None:
    body = payload("txn-invalid-time")
    body["timestamp"] = "2026-08-10T18:43:21"
    with TestClient(app) as client:
        response = client.post("/transactions", json=body)
    assert response.status_code == 422
