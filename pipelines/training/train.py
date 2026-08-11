from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from numpy.typing import NDArray
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
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
    imbalance = max((labels == 0).sum() / max((labels == 1).sum(), 1), 1)
    candidates: dict[str, Any] = {
        "logistic_regression": make_pipeline(
            StandardScaler(),
            LogisticRegression(class_weight="balanced", max_iter=1000, random_state=42),
        ),
        "random_forest": RandomForestClassifier(
            n_estimators=250,
            max_depth=14,
            min_samples_leaf=5,
            class_weight="balanced_subsample",
            n_jobs=-1,
            random_state=42,
        ),
    }
    try:
        from xgboost import XGBClassifier

        candidates["xgboost"] = XGBClassifier(
            n_estimators=350,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=imbalance,
            eval_metric="aucpr",
            random_state=42,
            n_jobs=-1,
        )
    except ImportError:
        print("MLflow is not installed; experiment was not tracked")
    except Exception as exc:
        print(f"MLflow tracking unavailable; model artifacts remain local: {exc}")
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


def train(data_path: Path, artifact_path: Path, report_path: Path) -> dict[str, object]:
    frame = pd.read_parquet(data_path).sort_values("timestamp").reset_index(drop=True)
    missing = set(FEATURE_COLUMNS + ["is_fraud", "amount"]) - set(frame.columns)
    if missing:
        raise ValueError(f"training data missing columns: {sorted(missing)}")
    if frame[FEATURE_COLUMNS].isna().any().any():
        raise ValueError("model features contain NaN values")
    splits = chronological_slices(len(frame))
    x, y = frame[FEATURE_COLUMNS], frame["is_fraud"].astype(int)
    costs = CostConfig()
    comparisons: dict[str, dict[str, float]] = {}
    trained: dict[str, Any] = {}
    for name, candidate in candidate_models(y.iloc[splits["train"]]).items():
        candidate.fit(x.iloc[splits["train"]], y.iloc[splits["train"]])
        probabilities = candidate.predict_proba(x.iloc[splits["selection"]])[:, 1]
        threshold = optimize_thresholds(
            y.iloc[splits["selection"]].to_numpy(),
            frame.iloc[splits["selection"]]["amount"].to_numpy(),
            probabilities,
            costs,
        )
        comparisons[name] = {
            **metrics(y.iloc[splits["selection"]].to_numpy(), probabilities, threshold[1]),
            "expected_cost": threshold[2],
        }
        trained[name] = candidate
    champion_name = min(
        comparisons,
        key=lambda name: (comparisons[name]["expected_cost"], -comparisons[name]["pr_auc"]),
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
    test_metrics = metrics(y.iloc[splits["test"]].to_numpy(), test_probability, block_threshold)
    test_cost = expected_cost(
        y.iloc[splits["test"]].to_numpy(),
        frame.iloc[splits["test"]]["amount"].to_numpy(),
        test_probability,
        review_threshold,
        block_threshold,
        costs,
    )
    fingerprint = hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).values).hexdigest()[
        :12
    ]
    version = f"{datetime.now(UTC):%Y%m%d%H%M%S}-{fingerprint}"
    reference_sample = frame.iloc[splits["calibration"]].sample(
        min(2000, len(frame.iloc[splits["calibration"]])), random_state=42
    )
    payload = {
        "model": calibrated,
        "version": version,
        "feature_columns": FEATURE_COLUMNS,
        "review_threshold": review_threshold,
        "block_threshold": block_threshold,
        "background": x.iloc[splits["calibration"]].sample(
            min(200, len(x.iloc[splits["calibration"]])), random_state=42
        ),
        "reference_distributions": {
            "amount": reference_sample["amount"].tolist(),
            "country": reference_sample["country"].astype(str).tolist(),
            "fraud_probability": calibrated.predict_proba(reference_sample[FEATURE_COLUMNS])[
                :, 1
            ].tolist(),
        },
    }
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(payload, artifact_path)
    report: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_fingerprint": fingerprint,
        "rows": len(frame),
        "champion": champion_name,
        "model_version": version,
        "splits": {name: part.stop - part.start for name, part in splits.items()},
        "candidate_selection_metrics": comparisons,
        "thresholds": {"review": review_threshold, "block": block_threshold},
        "threshold_period_expected_cost": threshold_cost,
        "test_metrics": test_metrics,
        "test_expected_cost": test_cost,
        "cost_config": asdict(costs),
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    try:
        import mlflow
        import mlflow.sklearn
        from mlflow.models import infer_signature

        mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "mlruns"))
        mlflow.set_experiment("fraud-detection-model-comparison")
        with mlflow.start_run(run_name=version):
            mlflow.log_params({"champion": champion_name, **asdict(costs)})
            mlflow.log_metrics({f"test_{key}": value for key, value in test_metrics.items()})
            mlflow.log_metrics({"test_expected_cost": test_cost})
            mlflow.log_artifact(str(report_path))
            input_example = x.iloc[splits["test"]].head(5)
            mlflow.sklearn.log_model(
                calibrated,
                "model",
                registered_model_name="fraud-detector",
                input_example=input_example,
                signature=infer_signature(input_example, calibrated.predict_proba(input_example)),
            )
    except ImportError:
        print("MLflow is not installed; experiment was not tracked")
    except Exception as exc:
        print(f"MLflow tracking unavailable; model artifacts remain local: {exc}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/processed/features.parquet"))
    parser.add_argument("--artifact", type=Path, default=Path("artifacts/models/champion.joblib"))
    parser.add_argument("--report", type=Path, default=Path("artifacts/model_report.json"))
    args = parser.parse_args()
    print(json.dumps(train(args.data, args.artifact, args.report), indent=2))


if __name__ == "__main__":
    main()
