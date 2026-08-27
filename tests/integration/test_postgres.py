from __future__ import annotations

from datetime import UTC, datetime

import pytest
from alembic.config import Config
from sqlalchemy import inspect, select, text

from alembic import command
from fraud_detection.config import get_settings
from fraud_detection.database import (
    ConfirmedLabelRecord,
    FraudAlertRecord,
    OutboxEventRecord,
    PredictionRecord,
    TransactionRecord,
    create_session_factory,
    score_and_persist,
    upsert_label,
)
from fraud_detection.decision import DecisionEngine
from fraud_detection.domain import ConfirmedLabel, Transaction

pytestmark = pytest.mark.integration


class AlwaysBlockModel:
    version = "integration-always-block"
    review_threshold = 0.10
    block_threshold = 0.30

    def predict_probability(self, features: dict[str, float]) -> float:
        del features
        return 0.95


def transaction(identifier: str, amount: float = 125.0) -> Transaction:
    return Transaction.model_validate(
        {
            "transaction_id": identifier,
            "user_id": "integration-user",
            "merchant_id": "integration-merchant",
            "timestamp": datetime.now(UTC),
            "amount": amount,
            "currency": "USD",
            "merchant_category": "electronics",
            "country": "US",
            "device_id": "integration-device",
            "ip_address": "192.0.2.40",
            "channel": "web",
        }
    )


def test_migrations_and_atomic_scoring(
    postgres_url: str,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    monkeypatch.setenv("DATABASE_URL", postgres_url)
    get_settings.cache_clear()
    request.addfinalizer(get_settings.cache_clear)
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", postgres_url)
    command.upgrade(config, "head")

    engine, factory = create_session_factory(postgres_url)
    assert {"transactions", "predictions", "fraud_alerts", "outbox_events"} <= set(
        inspect(engine).get_table_names()
    )
    with factory() as session:
        scored = score_and_persist(
            session,
            transaction("integration-block", amount=5000),
            AlwaysBlockModel(),
            DecisionEngine(0.10, 0.30),
        )
        session.commit()
        repeated = score_and_persist(
            session,
            transaction("integration-block", amount=5000),
            AlwaysBlockModel(),
            DecisionEngine(0.10, 0.30),
        )
        session.commit()
        assert repeated.transaction_id == scored.transaction_id
        assert repeated.decision == scored.decision
        assert repeated.fraud_probability == scored.fraud_probability
        assert repeated.model_version == scored.model_version
        assert session.scalar(
            select(TransactionRecord).where(
                TransactionRecord.transaction_id == scored.transaction_id
            )
        )
        assert session.scalar(
            select(PredictionRecord).where(
                PredictionRecord.transaction_id == scored.transaction_id
            )
        )
        assert session.scalar(
            select(FraudAlertRecord).where(
                FraudAlertRecord.transaction_id == scored.transaction_id
            )
        )
        outbox_events = session.scalars(
            select(OutboxEventRecord).where(
                OutboxEventRecord.event_key == scored.transaction_id
            )
        )
        assert len(list(outbox_events)) == 3

        upsert_label(
            session,
            scored.transaction_id,
            ConfirmedLabel(is_fraud=True, source="integration", confirmed_at=datetime.now(UTC)),
        )
        session.commit()
        assert session.get(ConfirmedLabelRecord, scored.transaction_id) is not None
        version = session.execute(text("SELECT version_num FROM alembic_version"))
        assert version.scalar_one() == "0004_promotion_idempotency"
