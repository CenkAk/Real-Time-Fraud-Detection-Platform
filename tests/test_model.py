from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from fraud_detection.model import load_model


class NamedFeatureModel:
    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        assert list(frame.columns) == ["amount", "velocity"]
        return np.array([[0.2, 0.8]])


def test_packaged_model_preserves_named_feature_order(tmp_path: Path) -> None:
    artifact = tmp_path / "model.joblib"
    joblib.dump(
        {
            "model": NamedFeatureModel(),
            "version": "test-v1",
            "review_threshold": 0.2,
            "block_threshold": 0.6,
            "feature_columns": ["amount", "velocity"],
        },
        artifact,
    )
    model = load_model(str(artifact))
    assert model.predict_probability({"velocity": 4.0, "amount": 100.0}) == 0.8
    assert model.review_threshold == 0.2
    assert model.block_threshold == 0.6
