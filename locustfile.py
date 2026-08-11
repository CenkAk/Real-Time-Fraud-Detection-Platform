from datetime import UTC, datetime
from uuid import uuid4

from locust import HttpUser, between, task


class FraudApiUser(HttpUser):
    wait_time = between(0.05, 0.2)

    @task
    def score_transaction(self) -> None:
        identifier = uuid4().hex
        self.client.post(
            "/transactions",
            json={
                "transaction_id": f"load-{identifier}",
                "user_id": f"user-{identifier[:4]}",
                "merchant_id": "merchant-load",
                "timestamp": datetime.now(UTC).isoformat(),
                "amount": 99.95,
                "currency": "USD",
                "merchant_category": "grocery",
                "country": "US",
                "device_id": f"device-{identifier[:4]}",
                "ip_address": "192.0.2.20",
                "channel": "web",
            },
            name="POST /transactions",
        )
