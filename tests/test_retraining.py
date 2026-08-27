import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from fraud_detection.database import (
    Base,
    ConfirmedLabelRecord,
    ModelPromotionRecord,
    PredictionRecord,
    RetrainingJobRecord,
    TransactionRecord,
    create_session_factory,
)
from fraud_detection.lifecycle import (
    drift_threshold_breached,
    evaluate_delayed_performance,
    queue_retraining_job,
)
from pipelines.retraining.promotion import promote_completed_job
from pipelines.retraining.run import compare_reports
from pipelines.retraining.worker import process_job, recover_interrupted_jobs


def test_challenger_is_never_automatically_promoted() -> None:
    champion = {
        "model_version": "v1",
        "test_expected_cost": 100,
        "test_metrics": {"pr_auc": 0.5, "recall": 0.7},
    }
    challenger = {
        "model_version": "v2",
        "test_expected_cost": 90,
        "test_metrics": {"pr_auc": 0.6, "recall": 0.8},
    }
    decision = compare_reports(champion, challenger)
    assert decision["promotion_recommended"] is True
    assert decision["automatic_promotion"] is False


def database_session() -> Session:
    engine, factory = create_session_factory("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    return factory()


def test_retraining_queue_is_idempotent_per_active_trigger() -> None:
    session = database_session()
    first = queue_retraining_job(
        session, trigger_type="DRIFT", champion_version="v1", metadata={"report": 1}
    )
    second = queue_retraining_job(
        session, trigger_type="DRIFT", champion_version="v1", metadata={"report": 2}
    )
    assert first.job_id == second.job_id
    assert session.query(RetrainingJobRecord).count() == 1


def test_automatic_trigger_is_deduplicated_after_challenger_completes() -> None:
    session = database_session()
    first = queue_retraining_job(
        session, trigger_type="DRIFT", champion_version="v1", metadata={"report": 1}
    )
    first.status = "COMPLETED"
    session.commit()

    repeated = queue_retraining_job(
        session, trigger_type="DRIFT", champion_version="v1", metadata={"report": 2}
    )
    assert repeated.job_id == first.job_id
    assert session.query(RetrainingJobRecord).count() == 1


def test_automatic_trigger_is_deduplicated_after_promotion() -> None:
    session = database_session()
    first = queue_retraining_job(
        session, trigger_type="DRIFT", champion_version="v1", metadata={"report": 1}
    )
    first.status = "PROMOTED"
    session.commit()

    repeated = queue_retraining_job(
        session, trigger_type="DRIFT", champion_version="v1", metadata={"report": 2}
    )
    assert repeated.job_id == first.job_id
    assert session.query(RetrainingJobRecord).count() == 1


def test_manual_trigger_can_be_repeated_after_completion() -> None:
    session = database_session()
    first = queue_retraining_job(
        session, trigger_type="MANUAL", champion_version="v1", metadata={}
    )
    first.status = "COMPLETED"
    session.commit()

    repeated = queue_retraining_job(
        session, trigger_type="MANUAL", champion_version="v1", metadata={}
    )
    assert repeated.job_id != first.job_id
    assert session.query(RetrainingJobRecord).count() == 2


def test_promotion_retry_returns_existing_audit_record() -> None:
    session = database_session()
    job = queue_retraining_job(
        session, trigger_type="MANUAL", champion_version="v1", metadata={}
    )
    job.status = "COMPLETED"
    job.promotion_recommended = True
    job.challenger_version = "2"
    audit = ModelPromotionRecord(
        job_id=job.job_id,
        previous_champion="1",
        promoted_version="2",
        promoted_by="analyst",
        gate_results={"passed": True},
    )
    session.add(audit)
    session.commit()

    retried = promote_completed_job(
        session,
        job,
        tracking_uri="http://mlflow-is-not-called",
        requested_by="analyst",
    )
    assert retried.promotion_id == audit.promotion_id
    assert job.status == "PROMOTED"
    assert session.query(ModelPromotionRecord).count() == 1


def test_interrupted_retraining_job_is_requeued() -> None:
    session = database_session()
    job = queue_retraining_job(
        session, trigger_type="DRIFT", champion_version="v1", metadata={}
    )
    job.status = "RUNNING"
    session.commit()
    assert recover_interrupted_jobs(session) == 1
    session.refresh(job)
    assert job.status == "QUEUED"
    assert job.trigger_metadata["recovery_count"] == 1


def test_drift_policy_uses_psi_and_js_thresholds() -> None:
    assert drift_threshold_breached({"amount": {"psi": 0.20}})
    assert drift_threshold_breached({"channel_js": 0.10})
    assert not drift_threshold_breached({"amount": {"psi": 0.19}, "channel_js": 0.09})


def test_delayed_performance_queues_job_after_200_labels(tmp_path: Path) -> None:
    session = database_session()
    now = datetime.now(UTC)
    for index in range(200):
        transaction_id = f"labeled-{index}"
        session.add(
            TransactionRecord(
                transaction_id=transaction_id,
                user_id="user",
                merchant_id="merchant",
                timestamp=now,
                amount=100.0,
                currency="USD",
                merchant_category="retail",
                country="US",
                device_id="device",
                ip_address="192.0.2.1",
                channel="web",
                request_id=transaction_id,
            )
        )
        session.add(
            PredictionRecord(
                transaction_id=transaction_id,
                fraud_probability=0.5,
                risk_score=50,
                decision="APPROVE",
                model_version="v1",
                processing_time_ms=1.0,
                rule_reasons=[],
                created_at=now - timedelta(hours=2),
            )
        )
        session.add(
            ConfirmedLabelRecord(
                transaction_id=transaction_id,
                is_fraud=index % 2 == 0,
                source="analyst",
                confirmed_at=now,
            )
        )
    session.commit()
    champion_report = tmp_path / "champion.json"
    champion_report.write_text(
        json.dumps(
            {
                "test_metrics": {"pr_auc": 0.9},
                "test_expected_cost": 10.0,
                "splits": {"test": 200},
            }
        ),
        encoding="utf-8",
    )
    report = evaluate_delayed_performance(
        session, model_version="v1", champion_report_path=champion_report
    )
    assert report is not None
    assert report.label_count == 200
    assert report.degradation_detected is True
    assert session.query(RetrainingJobRecord).one().trigger_type == "PERFORMANCE"


def test_completed_challenger_still_requires_manual_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("artifacts").mkdir()
    Path("artifacts/model_report.json").write_text(
        json.dumps(
            {
                "model_version": "champion-app",
                "test_expected_cost": 100,
                "test_metrics": {"pr_auc": 0.5, "recall": 0.7},
            }
        ),
        encoding="utf-8",
    )
    session = database_session()
    job = queue_retraining_job(
        session, trigger_type="MANUAL", champion_version="champion-app", metadata={}
    )
    session.commit()

    def trainer(_data: Path, _artifact: Path, _report: Path, _trials: int) -> dict[str, object]:
        return {
            "model_version": "challenger-app",
            "registered_model_version": "9",
            "test_expected_cost": 90,
            "test_metrics": {"pr_auc": 0.6, "recall": 0.8},
        }

    process_job(session, job, trainer=trainer, trials=1)
    session.refresh(job)
    assert job.status == "COMPLETED"
    assert job.promotion_recommended is True
    assert job.challenger_version == "9"
