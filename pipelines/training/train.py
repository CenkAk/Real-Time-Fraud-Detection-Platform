from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from numpy.typing import NDArray
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from pipelines.training.tracking import MlflowTracker
from pipelines.training.tuning import tune_tree_models

FEATURE_COLUMNS = [
    "amount",
    "hour",
    "weekday",
    "user_average_amount",
    "user_median_amount",
    "amount_vs_user_average",
    "transactions_last_5m",
    "transactions_last_1h",
    "transactions_last_24h",
    "new_merchant",
]


@dataclass(frozen=True)
class CostConfig:
    false_positive_cost: float = 25.0
    review_cost: float = 5.0
    review_catch_rate: float = 0.80
    max_review_rate: float = 0.05


def expected_cost(
    labels: NDArray[np.int_],
    amounts: NDArray[np.float64],
    probabilities: NDArray[np.float64],
    review_threshold: float,
    block_threshold: float,
    config: CostConfig,
) -> float:
    review = (probabilities >= review_threshold) & (probabilities < block_threshold)
    block = probabilities >= block_threshold
    approve = probabilities < review_threshold
    missed = amounts * labels * approve
    reviewed_fraud_loss = amounts * labels * review * (1 - config.review_catch_rate)
    friction = (~labels.astype(bool)) * block * config.false_positive_cost
    investigation = review * config.review_cost
    return float((missed + reviewed_fraud_loss + friction + investigation).sum())


def optimize_thresholds(
    labels: NDArray[np.int_],
    amounts: NDArray[np.float64],
    probabilities: NDArray[np.float64],
    config: CostConfig,
) -> tuple[float, float, float]:
    best = (0.40, 0.70, float("inf"))
    for review in np.arange(0.05, 0.81, 0.05):
        for block in np.arange(review + 0.05, 0.96, 0.05):
            review_rate = ((probabilities >= review) & (probabilities < block)).mean()
            if review_rate > config.max_review_rate:
                continue
            cost = expected_cost(
                labels, amounts, probabilities, float(review), float(block), config
            )
            if cost < best[2]:
                best = (round(float(review), 2), round(float(block), 2), cost)
    return best


def metrics(
    labels: NDArray[np.int_], probabilities: NDArray[np.float64], threshold: float
) -> dict[str, float]:
    predictions = probabilities >= threshold
    return {
        "precision": precision_score(labels, predictions, zero_division=0),
        "recall": recall_score(labels, predictions, zero_division=0),
        "f1": f1_score(labels, predictions, zero_division=0),
        "pr_auc": average_precision_score(labels, probabilities),
        "roc_auc": roc_auc_score(labels, probabilities),
        "false_positive_rate": float(
            ((predictions == 1) & (labels == 0)).sum() / max((labels == 0).sum(), 1)
        ),
        "false_negative_rate": float(
            ((predictions == 0) & (labels == 1)).sum() / max((labels == 1).sum(), 1)
        ),
    }


def candidate_models(labels: pd.Series) -> dict[str, Any]:
    del labels
    candidates: dict[str, Any] = {
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42),
        ),
    }
    try:
        from imblearn.over_sampling import SMOTE
        from imblearn.pipeline import make_pipeline as make_imbalance_pipeline
        from imblearn.under_sampling import RandomUnderSampler

        candidates["logistic_undersampled"] = make_imbalance_pipeline(
            RandomUnderSampler(random_state=42),
            StandardScaler(),
            LogisticRegression(max_iter=1000, random_state=42),
        )
        candidates["logistic_smote"] = make_imbalance_pipeline(
            SMOTE(random_state=42),
            StandardScaler(),
            LogisticRegression(max_iter=1000, random_state=42),
        )
    except ImportError:
        pass
    return candidates


def chronological_slices(size: int) -> dict[str, slice]:
    boundaries = [0, int(size * 0.50), int(size * 0.65), int(size * 0.75), int(size * 0.85), size]
    names = ["train", "selection", "calibration", "threshold", "test"]
    return {
        name: slice(boundaries[index], boundaries[index + 1]) for index, name in enumerate(names)
    }


def git_metadata() -> tuple[str, bool]:
    configured_sha = os.getenv("GIT_SHA")
    if configured_sha:
        return configured_sha, os.getenv("GIT_DIRTY", "false").lower() == "true"
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        return sha, dirty
    except (OSError, subprocess.CalledProcessError):
        return "unknown", False


def loggable_params(model: Any) -> dict[str, object]:
    params: dict[str, object] = {}
    for name, value in model.get_params(deep=True).items():
        if isinstance(value, (str, int, float, bool)) or value is None:
            params[name] = value
    return params


def train(
    data_path: Path,
    artifact_path: Path,
    report_path: Path,
    tuning_trials: int = 20,
) -> dict[str, object]:
    frame = pd.read_parquet(data_path).sort_values("timestamp").reset_index(drop=True)
    missing = set(FEATURE_COLUMNS + ["is_fraud", "amount"]) - set(frame.columns)
    if missing:
        raise ValueError(f"training data missing columns: {sorted(missing)}")
    if frame[FEATURE_COLUMNS].isna().any().any():
        raise ValueError("model features contain NaN values")
    splits = chronological_slices(len(frame))
    x, y = frame[FEATURE_COLUMNS], frame["is_fraud"].astype(int)
    costs = CostConfig()
    fingerprint = hashlib.sha256(
        pd.util.hash_pandas_object(frame, index=True).values
    ).hexdigest()
    git_sha, git_dirty = git_metadata()
    version = f"{datetime.now(UTC):%Y%m%d%H%M%S}-{fingerprint[:12]}"
    tracker = MlflowTracker(
        os.getenv("MLFLOW_TRACKING_URI", "mlruns"),
        {
            "dataset_fingerprint": fingerprint,
            "git_sha": git_sha,
            "git_dirty": git_dirty,
            "training_rows": len(frame),
        },
    )
    comparisons: dict[str, dict[str, float]] = {}
    trained: dict[str, Any] = {}

    selection_labels = y.iloc[splits["selection"]].to_numpy()
    selection_amounts = frame.iloc[splits["selection"]]["amount"].to_numpy()

    def evaluate_selection(probabilities: NDArray[np.float64]) -> dict[str, float]:
        threshold = optimize_thresholds(
            selection_labels,
            selection_amounts,
            probabilities,
            costs,
        )
        return {
            **metrics(selection_labels, probabilities, threshold[1]),
            "expected_cost": threshold[2],
            "review_threshold": threshold[0],
            "block_threshold": threshold[1],
        }

    with tracker.parent_run(version):
        for name, candidate in candidate_models(y.iloc[splits["train"]]).items():
            candidate.fit(x.iloc[splits["train"]], y.iloc[splits["train"]])
            probabilities = candidate.predict_proba(x.iloc[splits["selection"]])[:, 1]
            result = evaluate_selection(probabilities)
            comparisons[name] = result
            trained[name] = candidate
            tracker.nested_run(
                f"candidate-{name}",
                {"candidate": name, **loggable_params(candidate)},
                {f"selection_{key}": value for key, value in result.items()},
                {"run_type": "candidate"},
            )

        def log_trial(
            model_name: str,
            trial_number: int,
            params: dict[str, object],
            result: dict[str, float],
        ) -> None:
            tracker.nested_run(
                f"{model_name}-trial-{trial_number:03d}",
                {"candidate": model_name, "trial_number": trial_number, **params},
                {f"selection_{key}": value for key, value in result.items()},
                {"run_type": "tuning_trial", "model_family": model_name},
            )

        tuned, tuning_summary = tune_tree_models(
            x.iloc[splits["train"]],
            y.iloc[splits["train"]],
            x.iloc[splits["selection"]],
            tuning_trials,
            evaluate_selection,
            log_trial,
        )
        for name, candidate in tuned.items():
            probabilities = candidate.predict_proba(x.iloc[splits["selection"]])[:, 1]
            result = evaluate_selection(probabilities)
            comparisons[name] = result
            trained[name] = candidate
            tracker.nested_run(
                f"candidate-{name}-best",
                {"candidate": name, **loggable_params(candidate)},
                {f"selection_{key}": value for key, value in result.items()},
                {"run_type": "candidate", "tuned": "true"},
            )

        champion_name = min(
            comparisons,
            key=lambda name: (
                comparisons[name]["expected_cost"],
                -comparisons[name]["pr_auc"],
            ),
        )
        champion = trained[champion_name]
        fit_end = splits["selection"].stop
        champion.fit(x.iloc[:fit_end], y.iloc[:fit_end])
        calibrated = CalibratedClassifierCV(FrozenEstimator(champion), method="sigmoid")
        calibrated.fit(x.iloc[splits["calibration"]], y.iloc[splits["calibration"]])
        threshold_probability = calibrated.predict_proba(x.iloc[splits["threshold"]])[:, 1]
        review_threshold, block_threshold, threshold_cost = optimize_thresholds(
            y.iloc[splits["threshold"]].to_numpy(),
            frame.iloc[splits["threshold"]]["amount"].to_numpy(),
            threshold_probability,
            costs,
        )
        test_probability = calibrated.predict_proba(x.iloc[splits["test"]])[:, 1]
        test_metrics = metrics(
            y.iloc[splits["test"]].to_numpy(), test_probability, block_threshold
        )
        test_cost = expected_cost(
            y.iloc[splits["test"]].to_numpy(),
            frame.iloc[splits["test"]]["amount"].to_numpy(),
            test_probability,
            review_threshold,
            block_threshold,
            costs,
        )
        reference_sample = frame.iloc[splits["calibration"]].sample(
            min(2000, len(frame.iloc[splits["calibration"]])), random_state=42
        )
        feature_contract: dict[str, object] = {
            "schema_version": "1.0",
            "features": [
                {"name": column, "dtype": str(frame[column].dtype), "required": True}
                for column in FEATURE_COLUMNS
            ],
            "target": {"name": "is_fraud", "dtype": str(frame["is_fraud"].dtype)},
        }
        preprocessing_metadata: dict[str, object] = {
            "temporal_ordering": "timestamp ascending",
            "split_policy": "50/15/10/10/15 train-selection-calibration-threshold-test",
            "calibration_method": "sigmoid",
            "selection_policy": "minimum expected cost, PR-AUC tie-breaker",
            "test_usage": "single untouched final evaluation",
        }
        reference_distributions: dict[str, object] = {
            "amount": reference_sample["amount"].tolist(),
            "country": reference_sample["country"].astype(str).tolist(),
            "velocity": reference_sample["transactions_last_1h"].tolist(),
            "fraud_probability": calibrated.predict_proba(
                reference_sample[FEATURE_COLUMNS]
            )[:, 1].tolist(),
        }
        for categorical in ("merchant_category", "channel"):
            if categorical in reference_sample:
                reference_distributions[categorical] = (
                    reference_sample[categorical].astype(str).tolist()
                )
        payload = {
            "model": calibrated,
            "version": version,
            "feature_columns": FEATURE_COLUMNS,
            "feature_contract": feature_contract,
            "review_threshold": review_threshold,
            "block_threshold": block_threshold,
            "thresholds": {"review": review_threshold, "block": block_threshold},
            "preprocessing_metadata": preprocessing_metadata,
            "dataset_fingerprint": fingerprint,
            "git_sha": git_sha,
            "background": x.iloc[splits["calibration"]].sample(
                min(200, len(x.iloc[splits["calibration"]])), random_state=42
            ),
            "reference_distributions": reference_distributions,
        }
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(payload, artifact_path)
        report: dict[str, object] = {
            "generated_at": datetime.now(UTC).isoformat(),
            "dataset_fingerprint": fingerprint,
            "git_sha": git_sha,
            "git_dirty": git_dirty,
            "rows": len(frame),
            "champion": champion_name,
            "model_version": version,
            "registry_alias": "challenger",
            "automatic_production_promotion": False,
            "splits": {name: part.stop - part.start for name, part in splits.items()},
            "tuning_trials_per_tree_model": tuning_trials,
            "tuning_summary": tuning_summary,
            "candidate_selection_metrics": comparisons,
            "thresholds": {"review": review_threshold, "block": block_threshold},
            "threshold_period_expected_cost": threshold_cost,
            "test_metrics": test_metrics,
            "test_expected_cost": test_cost,
            "cost_config": asdict(costs),
            "feature_contract": feature_contract,
            "preprocessing_metadata": preprocessing_metadata,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        registered_version = tracker.log_final(
            calibrated,
            x.iloc[splits["test"]].head(5),
            report_path,
            artifact_path,
            {
                "champion_candidate": champion_name,
                "review_threshold": review_threshold,
                "block_threshold": block_threshold,
                **asdict(costs),
            },
            {
                **{f"test_{key}": value for key, value in test_metrics.items()},
                "test_expected_cost": test_cost,
                "threshold_period_expected_cost": threshold_cost,
            },
            feature_contract,
        )
        report["registered_model_version"] = registered_version
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/processed/features.parquet"))
    parser.add_argument("--artifact", type=Path, default=Path("artifacts/models/challenger.joblib"))
    parser.add_argument(
        "--report", type=Path, default=Path("artifacts/challenger_model_report.json")
    )
    parser.add_argument("--trials", type=int, default=20)
    args = parser.parse_args()
    print(json.dumps(train(args.data, args.artifact, args.report, args.trials), indent=2))


if __name__ == "__main__":
    main()
