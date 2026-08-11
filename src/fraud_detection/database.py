"""SQLAlchemy persistence model and transaction-safe scoring repository."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)
from sqlalchemy.pool import StaticPool

from fraud_detection.decision import DecisionEngine
from fraud_detection.domain import ConfirmedLabel, Decision, Prediction, Transaction
from fraud_detection.features import HistoryProvider
from fraud_detection.model import ProbabilityModel
from fraud_detection.service import ScoringService


class Base(DeclarativeBase):
    pass


class UserRecord(Base):
    __tablename__ = "users"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class MerchantRecord(Base):
    __tablename__ = "merchants"
    merchant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    category: Mapped[str] = mapped_column(String(64))
    country: Mapped[str] = mapped_column(String(2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class TransactionRecord(Base):
    __tablename__ = "transactions"
    transaction_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    merchant_id: Mapped[str] = mapped_column(ForeignKey("merchants.merchant_id"), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    merchant_category: Mapped[str] = mapped_column(String(64), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    prediction: Mapped[PredictionRecord | None] = relationship(back_populates="transaction")

    __table_args__ = (
        Index("ix_transactions_user_timestamp", "user_id", "timestamp"),
        Index("ix_transactions_timestamp", "timestamp"),
    )


class PredictionRecord(Base):
    __tablename__ = "predictions"
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transactions.transaction_id"), primary_key=True
    )
    fraud_probability: Mapped[float] = mapped_column(Float, nullable=False)
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    processing_time_ms: Mapped[float] = mapped_column(Float, nullable=False)
    rule_reasons: Mapped[list[str]] = mapped_column(JSON, default=list)
    feature_snapshot: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    transaction: Mapped[TransactionRecord] = relationship(back_populates="prediction")


class FraudAlertRecord(Base):
    __tablename__ = "fraud_alerts"
    alert_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transactions.transaction_id"), index=True
    )
    severity: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    explanation: Mapped[dict[str, object] | None] = mapped_column(JSON)
    analyst_note: Mapped[str | None] = mapped_column(Text)
    resolution: Mapped[str | None] = mapped_column(String(16))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ConfirmedLabelRecord(Base):
    __tablename__ = "confirmed_labels"
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transactions.transaction_id"), primary_key=True
    )
    is_fraud: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OutboxEventRecord(Base):
    __tablename__ = "outbox_events"
    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(128), nullable=False)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (Index("ix_outbox_unpublished", "published_at", "created_at"),)


class DriftReportRecord(Base):
    __tablename__ = "drift_reports"
    report_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    drift_detected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ModelVersionRecord(Base):
    __tablename__ = "model_versions"
    version: Mapped[str] = mapped_column(String(128), primary_key=True)
    stage: Mapped[str] = mapped_column(String(24), nullable=False)
    artifact_uri: Mapped[str] = mapped_column(Text, nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def create_session_factory(database_url: str) -> tuple[Engine, sessionmaker[Session]]:
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    if database_url.endswith(":memory:"):
        engine = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args=connect_args,
            poolclass=StaticPool,
        )
    else:
        engine = create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)
    return engine, sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def transaction_from_record(record: TransactionRecord) -> Transaction:
    timestamp = record.timestamp
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    return Transaction.model_validate(
        {
            "transaction_id": record.transaction_id,
            "user_id": record.user_id,
            "merchant_id": record.merchant_id,
            "timestamp": timestamp,
            "amount": record.amount,
            "currency": record.currency,
            "merchant_category": record.merchant_category,
            "country": record.country,
            "device_id": record.device_id,
            "ip_address": record.ip_address,
            "channel": record.channel,
            "latitude": record.latitude,
            "longitude": record.longitude,
            "request_id": record.request_id,
        }
    )


def prediction_from_record(record: PredictionRecord) -> Prediction:
    created_at = record.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return Prediction(
        transaction_id=record.transaction_id,
        fraud_probability=record.fraud_probability,
        risk_score=record.risk_score,
        decision=Decision(record.decision),
        model_version=record.model_version,
        processing_time_ms=record.processing_time_ms,
        rule_reasons=record.rule_reasons,
        created_at=created_at,
    )


class SQLHistoryProvider(HistoryProvider):
    def __init__(self, session: Session) -> None:
        self.session = session

    def prior_transactions(self, transaction: Transaction, days: int) -> Sequence[Transaction]:
        statement = (
            select(TransactionRecord)
            .where(
                TransactionRecord.user_id == transaction.user_id,
                TransactionRecord.timestamp >= transaction.timestamp - timedelta(days=days),
                TransactionRecord.timestamp < transaction.timestamp,
                TransactionRecord.transaction_id != transaction.transaction_id,
            )
            .order_by(TransactionRecord.timestamp)
        )
        return [transaction_from_record(row) for row in self.session.scalars(statement)]


def score_and_persist(
    session: Session,
    transaction: Transaction,
    model: ProbabilityModel,
    decision_engine: DecisionEngine,
) -> Prediction:
    """Idempotently score and atomically persist domain records plus outbox events."""

    existing = session.get(PredictionRecord, transaction.transaction_id)
    if existing is not None:
        return prediction_from_record(existing)

    session.merge(UserRecord(user_id=transaction.user_id))
    session.merge(
        MerchantRecord(
            merchant_id=transaction.merchant_id,
            category=transaction.merchant_category,
            country=transaction.country,
        )
    )
    scoring_service = ScoringService(SQLHistoryProvider(session), model, decision_engine)
    scoring = scoring_service.score_with_features(transaction)
    prediction = scoring.prediction
    session.add(
        TransactionRecord(
            transaction_id=transaction.transaction_id,
            user_id=transaction.user_id,
            merchant_id=transaction.merchant_id,
            timestamp=transaction.timestamp,
            amount=transaction.amount,
            currency=transaction.currency,
            merchant_category=transaction.merchant_category,
            country=transaction.country,
            device_id=transaction.device_id,
            ip_address=str(transaction.ip_address),
            channel=transaction.channel,
            latitude=transaction.latitude,
            longitude=transaction.longitude,
            request_id=str(transaction.request_id),
        )
    )
    session.add(
        PredictionRecord(
            transaction_id=prediction.transaction_id,
            fraud_probability=prediction.fraud_probability,
            risk_score=prediction.risk_score,
            decision=prediction.decision.value,
            model_version=prediction.model_version,
            processing_time_ms=prediction.processing_time_ms,
            rule_reasons=prediction.rule_reasons,
            feature_snapshot=scoring.feature_snapshot,
        )
    )
    session.add(
        OutboxEventRecord(
            topic="transactions.v1",
            event_key=transaction.transaction_id,
            payload=transaction.model_dump(mode="json"),
        )
    )
    session.add(
        OutboxEventRecord(
            topic="fraud_predictions.v1",
            event_key=transaction.transaction_id,
            payload=prediction.model_dump(mode="json"),
        )
    )
    if prediction.decision != Decision.APPROVE:
        alert = FraudAlertRecord(
            transaction_id=transaction.transaction_id,
            severity="HIGH" if prediction.decision == Decision.BLOCK else "MEDIUM",
        )
        session.add(alert)
        session.add(
            OutboxEventRecord(
                topic="fraud_alerts.v1",
                event_key=transaction.transaction_id,
                payload={
                    "transaction_id": transaction.transaction_id,
                    "decision": prediction.decision.value,
                    "risk_score": prediction.risk_score,
                    "rule_reasons": prediction.rule_reasons,
                },
            )
        )
    session.flush()
    return prediction


def upsert_label(session: Session, transaction_id: str, label: ConfirmedLabel) -> None:
    if session.get(TransactionRecord, transaction_id) is None:
        raise LookupError(transaction_id)
    session.merge(
        ConfirmedLabelRecord(
            transaction_id=transaction_id,
            is_fraud=label.is_fraud,
            source=label.source,
            confirmed_at=label.confirmed_at,
        )
    )
    session.add(
        OutboxEventRecord(
            topic="confirmed_labels.v1",
            event_key=transaction_id,
            payload={"transaction_id": transaction_id, **label.model_dump(mode="json")},
        )
    )
