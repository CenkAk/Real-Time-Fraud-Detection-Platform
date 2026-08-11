import numpy as np

from pipelines.training.train import CostConfig, expected_cost, optimize_thresholds


def test_missed_high_value_fraud_is_more_expensive() -> None:
    labels = np.array([1, 0])
    probabilities = np.array([0.1, 0.1])
    low = expected_cost(labels, np.array([10.0, 10.0]), probabilities, 0.4, 0.7, CostConfig())
    high = expected_cost(labels, np.array([1000.0, 10.0]), probabilities, 0.4, 0.7, CostConfig())
    assert high > low


def test_threshold_optimizer_returns_ordered_policy() -> None:
    labels = np.array([0, 0, 1, 1])
    amounts = np.array([10.0, 10.0, 100.0, 500.0])
    probabilities = np.array([0.01, 0.1, 0.8, 0.95])
    review, block, cost = optimize_thresholds(
        labels, amounts, probabilities, CostConfig(max_review_rate=0.5)
    )
    assert 0 <= review < block <= 1
    assert cost >= 0
