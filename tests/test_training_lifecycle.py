from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from pipelines.training.train import FEATURE_COLUMNS, train
from pipelines.training.tuning import tune_tree_models


def synthetic_frame(rows: int = 500) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    timestamps = [
        datetime(2025, 1, 1, tzinfo=UTC) + timedelta(minutes=index)
        for index in range(rows)
    ]
    amount = rng.uniform(5, 500, rows)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "amount": amount,
            "hour": np.arange(rows) % 24,
            "weekday": np.arange(rows) % 7,
            "user_average_amount": np.maximum(amount * 0.9, 1),
            "user_median_amount": np.maximum(amount * 0.8, 1),
            "amount_vs_user_average": amount / np.maximum(amount * 0.9, 1),
            "transactions_last_5m": np.arange(rows) % 5,
            "transactions_last_1h": np.arange(rows) % 20,
            "transactions_last_24h": np.arange(rows) % 50,
            "new_merchant": np.arange(rows) % 2,
            "country": np.where(np.arange(rows) % 2, "US", "GB"),
            "is_fraud": (np.arange(rows) % 10 == 0).astype(int),
        }
    )


def test_optuna_tunes_both_tree_families_and_logs_every_trial() -> None:
    frame = synthetic_frame(200)
    x = frame[FEATURE_COLUMNS]
    y = frame["is_fraud"]
    logged: list[tuple[str, int]] = []

    def evaluate(probabilities: np.ndarray) -> dict[str, float]:
        return {
            "expected_cost": float(probabilities.mean()),
            "pr_auc": float(1 - probabilities.mean()),
        }

    models, summaries = tune_tree_models(
        x.iloc[:120],
        y.iloc[:120],
        x.iloc[120:],
        1,
        evaluate,
        lambda name, trial, _params, _metrics: logged.append((name, trial)),
    )

    assert set(models) == {"random_forest", "xgboost"}
    assert set(summaries) == {"random_forest", "xgboost"}
    assert logged == [("random_forest", 0), ("xgboost", 0)]


def test_final_artifact_contains_lineage_contract_and_no_auto_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MLFLOW_TRACKING_DISABLED", "true")
    data_path = tmp_path / "features.parquet"
    artifact_path = tmp_path / "challenger.joblib"
    report_path = tmp_path / "report.json"
    synthetic_frame().to_parquet(data_path, index=False)

    report = train(data_path, artifact_path, report_path, tuning_trials=1)
    artifact = joblib.load(artifact_path)

    assert report["registry_alias"] == "challenger"
    assert report["automatic_production_promotion"] is False
    assert report["tuning_trials_per_tree_model"] == 1
    assert artifact["feature_contract"]["schema_version"] == "1.0"
    assert (
        artifact["preprocessing_metadata"]["test_usage"]
        == "single untouched final evaluation"
    )
    assert artifact["dataset_fingerprint"] == report["dataset_fingerprint"]
    assert artifact["thresholds"]["review"] < artifact["thresholds"]["block"]
