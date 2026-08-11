import numpy as np

from fraud_detection.drift import categorical_drift, numeric_drift


def test_drift_increases_for_shifted_distribution() -> None:
    reference = np.arange(100, dtype=float)
    stable = numeric_drift(reference, reference.copy())
    shifted = numeric_drift(reference, reference + 1000)
    assert stable["psi"] < shifted["psi"]
    assert stable["ks"] < shifted["ks"]


def test_categorical_drift_is_zero_for_same_distribution() -> None:
    assert categorical_drift(["US", "GB"], ["US", "GB"]) == 0
