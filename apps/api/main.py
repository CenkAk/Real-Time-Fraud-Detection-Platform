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
from fraud_detection.domain import (
    AlertResolution,
    AlertStatus,
    AlertUpdate,
    ConfirmedLabel,
    Decision,
    Prediction,
    Transaction,
)
from fraud_detection.explainability import reason_code_explanation
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


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _alert_payload(row: FraudAlertRecord | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "alert_id": row.alert_id,
        "transaction_id": row.transaction_id,
        "severity": row.severity,
        "status": row.status,
        "explanation": row.explanation,
        "analyst_note": row.analyst_note,
        "resolution": row.resolution,
        "resolved_at": _as_utc(row.resolved_at),
        "created_at": _as_utc(row.created_at),
    }


def _label_payload(row: ConfirmedLabelRecord | None) -> dict[str, object] | None:
    if row is None:
        return None
    return {
        "is_fraud": row.is_fraud,
        "source": row.source,
        "confirmed_at": _as_utc(row.confirmed_at),
    }


def _transaction_summary(
    transaction: TransactionRecord,
    prediction: PredictionRecord,
    alert: FraudAlertRecord | None,
    label: ConfirmedLabelRecord | None,
) -> dict[str, object]:
    return {
        "transaction_id": transaction.transaction_id,
        "timestamp": _as_utc(transaction.timestamp),
        "user_id": transaction.user_id,
        "merchant_id": transaction.merchant_id,
        "merchant_category": transaction.merchant_category,
        "amount": transaction.amount,
        "currency": transaction.currency,
        "country": transaction.country,
        "risk_score": prediction.risk_score,
        "fraud_probability": prediction.fraud_probability,
        "decision": prediction.decision,
        "model_version": prediction.model_version,
        "processing_time_ms": prediction.processing_time_ms,
        "case_status": alert.status if alert is not None else None,
        "resolution": alert.resolution if alert is not None else None,
        "confirmed_label": (
            AlertResolution.FRAUD.value if label is not None and label.is_fraud else
            AlertResolution.LEGITIMATE.value if label is not None else None
        ),
    }


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


@app.get("/transactions")
def list_transactions(
    hours: int = Query(default=24, ge=1, le=24 * 365),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    decision: Decision | None = Query(default=None),
    min_risk: int = Query(default=0, ge=0, le=100),
    max_risk: int = Query(default=100, ge=0, le=100),
    country: str | None = Query(default=None, min_length=2, max_length=2),
    merchant_category: str | None = Query(default=None, min_length=1, max_length=64),
    min_amount: float | None = Query(default=None, ge=0),
    session: Session = Depends(database_session),
) -> dict[str, object]:
    if min_risk > max_risk:
        raise HTTPException(422, "min_risk cannot be greater than max_risk")
    since = datetime.now(UTC) - timedelta(hours=hours)
    filters = [
        TransactionRecord.timestamp >= since,
        PredictionRecord.risk_score >= min_risk,
        PredictionRecord.risk_score <= max_risk,
    ]
    if decision is not None:
        filters.append(PredictionRecord.decision == decision.value)
    if country is not None:
        filters.append(TransactionRecord.country == country.upper())
    if merchant_category is not None:
        filters.append(TransactionRecord.merchant_category == merchant_category)
    if min_amount is not None:
        filters.append(TransactionRecord.amount >= min_amount)

    total = session.scalar(
        select(func.count())
        .select_from(TransactionRecord)
        .join(PredictionRecord)
        .where(*filters)
    ) or 0
    rows = session.execute(
        select(
            TransactionRecord,
            PredictionRecord,
            FraudAlertRecord,
            ConfirmedLabelRecord,
        )
        .join(PredictionRecord)
        .outerjoin(
            FraudAlertRecord,
            FraudAlertRecord.transaction_id == TransactionRecord.transaction_id,
        )
        .outerjoin(
            ConfirmedLabelRecord,
            ConfirmedLabelRecord.transaction_id == TransactionRecord.transaction_id,
        )
        .where(*filters)
        .order_by(TransactionRecord.timestamp.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return {
        "items": [_transaction_summary(*row) for row in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "as_of": datetime.now(UTC),
    }


@app.get("/transactions/{transaction_id}", response_model=Transaction)
def get_transaction(
    transaction_id: str, session: Session = Depends(database_session)
) -> Transaction:
    row = session.get(TransactionRecord, transaction_id)
    if row is None:
        raise HTTPException(404, "transaction not found")
    return transaction_from_record(row)


@app.get("/transactions/{transaction_id}/investigation")
def investigate_transaction(
    transaction_id: str, session: Session = Depends(database_session)
) -> dict[str, object]:
    transaction_row = session.get(TransactionRecord, transaction_id)
    prediction_row = session.get(PredictionRecord, transaction_id)
    if transaction_row is None or prediction_row is None:
        raise HTTPException(404, "transaction or prediction not found")
    alert = session.scalar(
        select(FraudAlertRecord).where(FraudAlertRecord.transaction_id == transaction_id)
    )
    label = session.get(ConfirmedLabelRecord, transaction_id)
    snapshot = prediction_row.feature_snapshot
    if alert is not None and alert.explanation is not None:
        explanation_status = "complete"
        explanation = alert.explanation
    elif snapshot is not None:
        explanation_status = "fallback"
        explanation = {
            "method": "reason_codes",
            "top_risk_factors": [
                factor.model_dump() for factor in reason_code_explanation(snapshot)
            ],
        }
    else:
        explanation_status = "unavailable"
        explanation = {"method": None, "top_risk_factors": []}

    recent_rows = session.execute(
        select(TransactionRecord, PredictionRecord)
        .join(PredictionRecord)
        .where(
            TransactionRecord.user_id == transaction_row.user_id,
            TransactionRecord.transaction_id != transaction_id,
            TransactionRecord.timestamp <= transaction_row.timestamp,
        )
        .order_by(TransactionRecord.timestamp.desc())
        .limit(10)
    ).all()
    recent = [
        {
            "transaction_id": transaction.transaction_id,
            "timestamp": _as_utc(transaction.timestamp),
            "amount": transaction.amount,
            "currency": transaction.currency,
            "country": transaction.country,
            "merchant_id": transaction.merchant_id,
            "risk_score": prediction.risk_score,
            "decision": prediction.decision,
        }
        for transaction, prediction in recent_rows
    ]
    return {
        "transaction": transaction_from_record(transaction_row),
        "prediction": prediction_from_record(prediction_row),
        "feature_snapshot": snapshot,
        "feature_snapshot_status": "available" if snapshot is not None else "unavailable",
        "explanation_status": explanation_status,
        "explanation": explanation,
        "alert": _alert_payload(alert),
        "confirmed_label": _label_payload(label),
        "recent_user_transactions": recent,
    }


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
    payloads: list[dict[str, object]] = []
    for row in rows:
        payload = _alert_payload(row)
        if payload is not None:
            payloads.append(payload)
    return payloads


@app.patch("/alerts/{alert_id}")
def update_alert(
    alert_id: int,
    update: AlertUpdate,
    session: Session = Depends(database_session),
) -> dict[str, object]:
    alert = session.get(FraudAlertRecord, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    if alert.status == AlertStatus.RESOLVED.value:
        if (
            update.status == AlertStatus.RESOLVED
            and update.resolution is not None
            and update.resolution.value == alert.resolution
        ):
            if update.analyst_note is not None:
                alert.analyst_note = update.analyst_note
                session.commit()
            payload = _alert_payload(alert)
            assert payload is not None
            return payload
        raise HTTPException(409, "resolved alert cannot be transitioned or relabeled")
    if alert.status == AlertStatus.IN_REVIEW.value and update.status == AlertStatus.OPEN:
        raise HTTPException(409, "an in-review alert cannot return to OPEN")

    alert.status = update.status.value
    if update.analyst_note is not None:
        alert.analyst_note = update.analyst_note
    if update.status == AlertStatus.RESOLVED:
        assert update.resolution is not None
        confirmed_at = datetime.now(UTC)
        alert.resolution = update.resolution.value
        alert.resolved_at = confirmed_at
        upsert_label(
            session,
            alert.transaction_id,
            ConfirmedLabel(
                is_fraud=update.resolution == AlertResolution.FRAUD,
                source="analyst",
                confirmed_at=confirmed_at,
            ),
        )
    session.commit()
    payload = _alert_payload(alert)
    assert payload is not None
    return payload


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
