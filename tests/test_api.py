import math
import os
from datetime import UTC, datetime, timedelta
from importlib import import_module

from fastapi.testclient import TestClient

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

api_module = import_module("apps.api.main")
database_module = import_module("fraud_detection.database")
SessionFactory = api_module.SessionFactory
app = api_module.app
PredictionRecord = database_module.PredictionRecord
database_module.Base.metadata.create_all(api_module.engine)


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


def suspicious_pair(identifier: str) -> tuple[dict[str, object], dict[str, object]]:
    earlier = payload(f"{identifier}-baseline")
    earlier.update(
        {
            "user_id": f"user-{identifier}",
            "timestamp": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
            "amount": 25.0,
            "latitude": 40.7128,
            "longitude": -74.0060,
        }
    )
    suspicious = payload(identifier)
    suspicious.update(
        {
            "user_id": f"user-{identifier}",
            "timestamp": datetime.now(UTC).isoformat(),
            "amount": 2500.0,
            "country": "JP",
            "device_id": f"new-device-{identifier}",
            "latitude": 35.6762,
            "longitude": 139.6503,
        }
    )
    return earlier, suspicious


def test_transaction_feed_filters_and_investigation_snapshot() -> None:
    earlier, suspicious = suspicious_pair("txn-investigation")
    with TestClient(app) as client:
        assert client.post("/transactions", json=earlier).status_code == 200
        scored = client.post("/transactions", json=suspicious)
        feed = client.get(
            "/transactions",
            params={"decision": "BLOCK", "country": "jp", "min_risk": 1},
        )
        detail_before = client.get("/transactions/txn-investigation/investigation")
        later = payload("txn-investigation-later")
        later.update({"user_id": "user-txn-investigation", "amount": 10.0})
        assert client.post("/transactions", json=later).status_code == 200
        detail_after = client.get("/transactions/txn-investigation/investigation")

    assert scored.status_code == 200
    assert scored.json()["decision"] == "BLOCK"
    assert feed.status_code == 200
    assert feed.json()["total"] >= 1
    assert feed.json()["items"][0]["transaction_id"] == "txn-investigation"
    assert detail_before.status_code == 200
    before_snapshot = detail_before.json()["feature_snapshot"]
    assert detail_before.json()["feature_snapshot_status"] == "available"
    assert before_snapshot == detail_after.json()["feature_snapshot"]
    assert "transactions_last_5m" in before_snapshot
    assert all(math.isfinite(float(value)) for value in before_snapshot.values())
    impacts = [
        abs(float(factor["impact"]))
        for factor in detail_before.json()["explanation"]["top_risk_factors"]
    ]
    assert impacts == sorted(impacts, reverse=True)


def test_alert_review_and_resolution_are_atomic_and_idempotent() -> None:
    earlier, suspicious = suspicious_pair("txn-case-workflow")
    with TestClient(app) as client:
        client.post("/transactions", json=earlier)
        client.post("/transactions", json=suspicious)
        alerts = client.get("/alerts?limit=1000").json()
        alert = next(row for row in alerts if row["transaction_id"] == "txn-case-workflow")
        alert_id = alert["alert_id"]

        in_review = client.patch(
            f"/alerts/{alert_id}",
            json={"status": "IN_REVIEW", "analyst_note": "Investigating device takeover."},
        )
        cannot_reopen = client.patch(f"/alerts/{alert_id}", json={"status": "OPEN"})
        missing_resolution = client.patch(
            f"/alerts/{alert_id}", json={"status": "RESOLVED"}
        )
        resolved = client.patch(
            f"/alerts/{alert_id}",
            json={
                "status": "RESOLVED",
                "resolution": "FRAUD",
                "analyst_note": "Confirmed account takeover.",
            },
        )
        repeated = client.patch(
            f"/alerts/{alert_id}",
            json={"status": "RESOLVED", "resolution": "FRAUD"},
        )
        conflicting = client.patch(
            f"/alerts/{alert_id}",
            json={"status": "RESOLVED", "resolution": "LEGITIMATE"},
        )
        detail = client.get("/transactions/txn-case-workflow/investigation")

    assert in_review.status_code == 200
    assert in_review.json()["status"] == "IN_REVIEW"
    assert cannot_reopen.status_code == 409
    assert missing_resolution.status_code == 422
    assert resolved.status_code == 200
    assert resolved.json()["resolution"] == "FRAUD"
    assert repeated.status_code == 200
    assert conflicting.status_code == 409
    assert detail.json()["confirmed_label"]["is_fraud"] is True
    assert detail.json()["alert"]["resolved_at"] is not None


def test_alert_and_filter_validation_errors() -> None:
    with TestClient(app) as client:
        missing_alert = client.patch("/alerts/999999", json={"status": "IN_REVIEW"})
        invalid_range = client.get("/transactions?min_risk=80&max_risk=20")
    assert missing_alert.status_code == 404
    assert invalid_range.status_code == 422


def test_historical_prediction_without_snapshot_has_safe_fallback() -> None:
    with TestClient(app) as client:
        client.post("/transactions", json=payload("txn-old-prediction"))
        with SessionFactory() as session:
            prediction = session.get(PredictionRecord, "txn-old-prediction")
            assert prediction is not None
            prediction.feature_snapshot = None
            session.commit()
        detail = client.get("/transactions/txn-old-prediction/investigation")

    assert detail.status_code == 200
    assert detail.json()["feature_snapshot"] is None
    assert detail.json()["feature_snapshot_status"] == "unavailable"
    assert detail.json()["explanation"]["top_risk_factors"] == []


def test_analytics_contracts_and_request_correlation() -> None:
    earlier, suspicious = suspicious_pair("txn-analytics-contract")
    with TestClient(app) as client:
        client.post("/transactions", json=earlier)
        scored = client.post("/transactions", json=suspicious)
        assert scored.json()["decision"] == "BLOCK"
        alerts = client.get("/alerts?limit=1000").json()
        alert = next(row for row in alerts if row["transaction_id"] == "txn-analytics-contract")
        client.patch(
            f"/alerts/{alert['alert_id']}",
            json={"status": "RESOLVED", "resolution": "FRAUD"},
        )

        overview = client.get(
            "/analytics/overview", headers={"x-request-id": "analytics-contract-request"}
        )
        trends = client.get("/analytics/fraud-trends?dimension=country&hours=24")
        performance = client.get("/analytics/model-performance")
        drift = client.get("/analytics/drift-reports?limit=10&offset=0")
        metrics = client.get("/metrics")

    assert overview.status_code == 200
    assert overview.headers["x-request-id"] == "analytics-contract-request"
    assert overview.json()["confirmed_fraud_24h"] >= 1
    assert overview.json()["confirmed_fraud_blocked_amount_24h"] >= 2500
    assert any(row["key"] == "JP" for row in trends.json())
    assert performance.json()["status"] == "available"
    assert performance.json()["labeled_transactions"] >= 1
    assert drift.json()["items"] == []
    assert drift.json()["limit"] == 10
    assert "fraud_http_requests_total" in metrics.text


def test_manual_retraining_request_only_queues_a_job() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/admin/retraining-jobs",
            json={"requested_by": "phase5-test", "reason": "manual verification"},
        )
        jobs = client.get("/admin/retraining-jobs")
    assert response.status_code == 202
    assert response.json()["status"] == "QUEUED"
    assert response.json()["promotion_recommended"] is None
    assert any(row["job_id"] == response.json()["job_id"] for row in jobs.json())
