"""Model loading and a transparent fallback scorer for bootstrap operation."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, cast

import joblib
import numpy as np
import pandas as pd
from numpy.typing import NDArray


class ProbabilityModel(Protocol):
    version: str
    review_threshold: float
    block_threshold: float

    def predict_probability(self, features: dict[str, float]) -> float: ...


class ProbabilityEstimator(Protocol):
    def predict_proba(self, features: pd.DataFrame) -> NDArray[np.float64]: ...


class HeuristicBootstrapModel:
    """Explicit non-ML fallback used only until a trained model is available."""

    version = "bootstrap-heuristic"
    review_threshold = 0.40
    block_threshold = 0.70

    def predict_probability(self, features: dict[str, float]) -> float:
        logit = -4.0
        logit += min(features.get("amount_vs_user_average", 1.0), 15) * 0.12
        logit += min(features.get("transactions_last_5m", 0), 10) * 0.22
        logit += features.get("new_device", 0) * 0.8
        logit += features.get("new_country", 0) * 0.7
        logit += features.get("impossible_travel", 0) * 2.0
        return float(1 / (1 + np.exp(-logit)))


class SklearnModel:
    def __init__(
        self,
        artifact: object,
        version: str,
        review: float,
        block: float,
        feature_columns: list[str] | None = None,
    ) -> None:
        self.artifact = artifact
        self.version = version
        self.review_threshold = review
        self.block_threshold = block
        self.feature_columns = feature_columns

    def predict_probability(self, features: dict[str, float]) -> float:
        columns = self.feature_columns or list(features)
        frame = pd.DataFrame([{name: features.get(name, 0.0) for name in columns}])
        estimator = cast(ProbabilityEstimator, self.artifact)
        probability = estimator.predict_proba(frame)[0][1]
        return float(probability)


def load_model(path: str) -> ProbabilityModel:
    artifact_path = Path(path)
    if not artifact_path.exists():
        return HeuristicBootstrapModel()
    payload = joblib.load(artifact_path)
    if isinstance(payload, dict) and "model" in payload:
        return SklearnModel(
            payload["model"],
            str(payload.get("version", artifact_path.stem)),
            float(payload.get("review_threshold", 0.40)),
            float(payload.get("block_threshold", 0.70)),
            list(payload.get("feature_columns", [])) or None,
        )
    return SklearnModel(payload, artifact_path.stem, 0.40, 0.70)
