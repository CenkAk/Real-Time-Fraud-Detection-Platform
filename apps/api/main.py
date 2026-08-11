"""FastAPI entrypoint for scoring and operational queries."""

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Query, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from fraud_detection.config import get_settings
from fraud_detection.database import (
    Base,
    ConfirmedLabelRecord,
    FraudAlertRecord,
    PredictionRecord,
    TransactionRecord,
    create_session_factory,
    prediction_from_record,
    score_and_persist,
    transaction_from_record,
    upsert_label,
)
from fraud_detection.decision import DecisionEngine
from fraud_detection.domain import ConfirmedLabel, Prediction, Transaction
from fraud_detection.model import load_model
from fraud_detection.observability import INFERENCE_LATENCY, TRANSACTIONS, configure_logging

settings = get_settings()
engine, SessionFactory = create_session_factory(settings.database_url)
model = load_model(settings.model_path)
decision_engine = DecisionEngine(
    review_threshold=(
        model.review_threshold if settings.use_model_thresholds else settings.fraud_review_threshold
    ),
    block_threshold=(
        model.block_threshold if settings.use_model_thresholds else settings.fraud_block_threshold
    ),
)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title="Real-Time Fraud Detection Platform",
    version="0.1.0",
    description="Synchronous risk scoring backed by event-driven processing.",
    lifespan=lifespan,
)


def database_session() -> Iterator[Session]:
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


@app.post("/transactions", response_model=Prediction)
def create_transaction(
    transaction: Transaction, session: Session = Depends(database_session)
) -> Prediction:
    try:
        with INFERENCE_LATENCY.time():
            prediction = score_and_persist(session, transaction, model, decision_engine)
            session.commit()
        TRANSACTIONS.labels(prediction.decision.value).inc()
        return prediction
    except Exception:
        session.rollback()
        raise


@app.get("/transactions/{transaction_id}", response_model=Transaction)
def get_transaction(
    transaction_id: str, session: Session = Depends(database_session)
) -> Transaction:
    row = session.get(TransactionRecord, transaction_id)
    if row is None:
        raise HTTPException(404, "transaction not found")
    return transaction_from_record(row)


@app.get("/predictions/{transaction_id}", response_model=Prediction)
def get_prediction(transaction_id: str, session: Session = Depends(database_session)) -> Prediction:
    row = session.get(PredictionRecord, transaction_id)
    if row is None:
        raise HTTPException(404, "prediction not found")
    return prediction_from_record(row)


@app.get("/predictions/{transaction_id}/explanation")
def get_explanation(
    transaction_id: str, session: Session = Depends(database_session)
) -> dict[str, object]:
    alert = session.scalar(
        select(FraudAlertRecord).where(FraudAlertRecord.transaction_id == transaction_id)
    )
    if alert is None:
        raise HTTPException(404, "alert not found for transaction")
    if alert.explanation is None:
        return {"status": "pending", "transaction_id": transaction_id}
    return {"status": "complete", "transaction_id": transaction_id, **alert.explanation}


@app.get("/alerts")
def get_alerts(
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(database_session),
) -> list[dict[str, object]]:
    rows = session.scalars(
        select(FraudAlertRecord).order_by(FraudAlertRecord.created_at.desc()).limit(limit)
    )
    return [
        {
            "alert_id": row.alert_id,
            "transaction_id": row.transaction_id,
            "severity": row.severity,
            "status": row.status,
            "explanation": row.explanation,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@app.post("/transactions/{transaction_id}/label", status_code=204)
def label_transaction(
    transaction_id: str,
    label: ConfirmedLabel,
    session: Session = Depends(database_session),
) -> Response:
    try:
        upsert_label(session, transaction_id, label)
        session.commit()
    except LookupError:
        session.rollback()
        raise HTTPException(404, "transaction not found") from None
    return Response(status_code=204)


@app.get("/analytics/overview")
def analytics_overview(session: Session = Depends(database_session)) -> dict[str, object]:
    since = datetime.now(UTC) - timedelta(days=1)
    total = (
        session.scalar(
            select(func.count())
            .select_from(TransactionRecord)
            .where(TransactionRecord.timestamp >= since)
        )
        or 0
    )
    grouped = session.execute(
        select(PredictionRecord.decision, func.count())
        .join(TransactionRecord)
        .where(TransactionRecord.timestamp >= since)
        .group_by(PredictionRecord.decision)
    ).all()
    return {
        "transactions_24h": total,
        "decisions": {name: count for name, count in grouped},
        "as_of": datetime.now(UTC),
    }


@app.get("/analytics/risk-distribution")
def risk_distribution(session: Session = Depends(database_session)) -> list[dict[str, int]]:
    rows = session.execute(
        select(PredictionRecord.risk_score, func.count())
        .group_by(PredictionRecord.risk_score)
        .order_by(PredictionRecord.risk_score)
    ).all()
    return [{"risk_score": score, "count": count} for score, count in rows]


@app.get("/analytics/model-performance")
def model_performance(session: Session = Depends(database_session)) -> dict[str, object]:
    rows = session.execute(
        select(
            ConfirmedLabelRecord.is_fraud,
            PredictionRecord.fraud_probability,
            PredictionRecord.decision,
        ).join(
            PredictionRecord, PredictionRecord.transaction_id == ConfirmedLabelRecord.transaction_id
        )
    ).all()
    if not rows:
        return {"status": "awaiting_labels", "labeled_transactions": 0}
    labels = [int(row.is_fraud) for row in rows]
    predicted = [int(row.decision == "BLOCK") for row in rows]
    true_positive = sum(
        actual == 1 and guess == 1 for actual, guess in zip(labels, predicted, strict=True)
    )
    false_positive = sum(
        actual == 0 and guess == 1 for actual, guess in zip(labels, predicted, strict=True)
    )
    false_negative = sum(
        actual == 1 and guess == 0 for actual, guess in zip(labels, predicted, strict=True)
    )
    precision = true_positive / max(true_positive + false_positive, 1)
    recall = true_positive / max(true_positive + false_negative, 1)
    return {
        "status": "available",
        "labeled_transactions": len(rows),
        "precision": precision,
        "recall": recall,
        "f1": 2 * prec…23938 tokens truncated… * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
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
