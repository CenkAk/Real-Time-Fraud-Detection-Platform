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
        "f1": 2 * precision * recall / max(precision + recall, 1e-12),
    }


@app.get("/model/info")
def model_info() -> dict[str, object]:
    return {
        "model_version": model.version,
        "review_threshold": decision_engine.review_threshold,
        "block_threshold": decision_engine.block_threshold,
        "bootstrap_model": model.version == "bootstrap-heuristic",
    }


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "alive"}


@app.get("/health/ready")
def readiness(session: Session = Depends(database_session)) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.get("/health")
def health(session: Session = Depends(database_session)) -> dict[str, object]:
    session.execute(text("SELECT 1"))
    return {"status": "healthy", "model_version": model.version}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
