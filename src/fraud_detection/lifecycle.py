from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sklearn.metrics import average_precision_score, brier_score_loss
from sqlalchemy import select
from sqlalchemy.orm import Session

from fraud_detection.database import (
    ConfirmedLabelRecord,
    PerformanceReportRecord,
    PredictionRecord,
    RetrainingJobRecord,
    TransactionRecord,
)

MINIMUM_LABELS = 200
PR_AUC_RELATIVE_DROP = 0.10
EXPECTED_COST_INCREASE = 0.15


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def queue_retraining_job(
    session: Session,
    *,
    trigger_type: str,
    champion_version: str,
    metadata: dict[str, object],
    requested_by: str = "system",
) -> RetrainingJobRecord:
    # Automatic signals describe a degradation episode for the current champion.
    # Once that episode has produced a challenger, repeated monitor windows must
    # not start the same expensive training run again. Promoting a new champion
    # changes champion_version and therefore opens a new episode. Manual requests
    # remain repeatable after their previous run has finished.
    deduplicated_statuses = ["QUEUED", "RUNNING"]
    if trigger_type in {"DRIFT", "PERFORMANCE"}:
        deduplicated_statuses.extend(["COMPLETED", "PROMOTED"])
    active = session.scalar(
        select(RetrainingJobRecord)
        .where(
            RetrainingJobRecord.trigger_type == trigger_type,
            RetrainingJobRecord.champion_version == champion_version,
            RetrainingJobRecord.status.in_(deduplicated_statuses),
        )
        .order_by(RetrainingJobRecord.created_at.desc())
    )
    if active is not None:
        return active
    job = RetrainingJobRecord(
        job_id=str(uuid4()),
        trigger_type=trigger_type,
        trigger_metadata=metadata,
        champion_version=champion_version,
        requested_by=requested_by,
    )
    session.add(job)
    session.flush()
    return job


def drift_threshold_breached(metrics: dict[str, object]) -> bool:
    for key, value in metrics.items():
        if isinstance(value, dict):
            psi = value.get("psi")
            if isinstance(psi, (int, float)) and psi >= 0.20:
                return True
            js = value.get("js")
            if isinstance(js, (int, float)) and js >= 0.10:
                return True
        if isinstance(value, (int, float)) and key.endswith("_js"):
            return value >= 0.10
    return False


def evaluate_delayed_performance(
    session: Session,
    *,
    model_version: str,
    champion_report_path: Path,
) -> PerformanceReportRecord | None:
    rows = session.execute(
        select(
            ConfirmedLabelRecord.is_fraud,
            ConfirmedLabelRecord.confirmed_at,
            PredictionRecord.fraud_probability,
            PredictionRecord.decision,
            PredictionRecord.created_at,
            TransactionRecord.amount,
        )
        .join(
            PredictionRecord,
            PredictionRecord.transaction_id == ConfirmedLabelRecord.transaction_id,
        )
        .join(
            TransactionRecord,
            TransactionRecord.transaction_id == ConfirmedLabelRecord.transaction_id,
        )
        .where(PredictionRecord.model_version == model_version)
        .order_by(ConfirmedLabelRecord.confirmed_at)
    ).all()
    if len(rows) < MINIMUM_LABELS:
        return None

    reference = json.loads(champion_report_path.read_text(encoding="utf-8"))
    labels = [int(row.is_fraud) for row in rows]
    probabilities = [float(row.fraud_probability) for row in rows]
    current_pr_auc = float(average_precision_score(labels, probabilities))
    current_brier = float(brier_score_loss(labels, probabilities))
    current_cost = 0.0
    for row in rows:
        if row.is_fraud and row.decision == "APPROVE":
            current_cost += float(row.amount)
        elif row.is_fraud and row.decision == "MANUAL_REVIEW":
            current_cost += float(row.amount) * 0.20 + 5.0
        elif not row.is_fraud and row.decision == "BLOCK":
            current_cost += 25.0
        elif row.decision == "MANUAL_REVIEW":
            current_cost += 5.0
    current_cost_per_transaction = current_cost / len(rows)
    reference_pr_auc = float(reference["test_metrics"]["pr_auc"])
    reference_rows = int(reference["splits"]["test"])
    reference_cost_per_transaction = float(reference["test_expected_cost"]) / reference_rows
    pr_auc_relative_drop = (reference_pr_auc - current_pr_auc) / max(reference_pr_auc, 1e-12)
    cost_increase = (
        current_cost_per_transaction - reference_cost_per_transaction
    ) / max(reference_cost_per_transaction, 1e-12)
    label_delays = [
        max((_utc(row.confirmed_at) - _utc(row.created_at)).total_seconds(), 0) / 3600
        for row in rows
    ]
    metrics: dict[str, object] = {
        "pr_auc": current_pr_auc,
        "reference_pr_auc": reference_pr_auc,
        "pr_auc_relative_drop": pr_auc_relative_drop,
        "expected_cost_per_transaction": current_cost_per_transaction,
        "reference_expected_cost_per_transaction": reference_cost_per_transaction,
        "expected_cost_increase": cost_increase,
        "brier_score": current_brier,
        "label_delay_hours_mean": sum(label_delays) / len(label_delays),
    }
    degraded = (
        pr_auc_relative_drop >= PR_AUC_RELATIVE_DROP
        or cost_increase >= EXPECTED_COST_INCREASE
    )
    report = PerformanceReportRecord(
        model_version=model_version,
        window_start=_utc(rows[0].confirmed_at),
        window_end=datetime.now(UTC),
        label_count=len(rows),
        metrics=metrics,
        degradation_detected=degraded,
    )
    session.add(report)
    session.flush()
    if degraded:
        queue_retraining_job(
            session,
            trigger_type="PERFORMANCE",
            champion_version=model_version,
            metadata={"performance_report_id": report.report_id, **metrics},
        )
    return report
