import pytest

from fraud_detection.decision import DecisionEngine
from fraud_detection.domain import Decision


@pytest.mark.parametrize(
    ("probability", "expected"),
    [(0.39, Decision.APPROVE), (0.40, Decision.MANUAL_REVIEW), (0.70, Decision.BLOCK)],
)
def test_threshold_boundaries(probability: float, expected: Decision) -> None:
    assert DecisionEngine().decide(probability, {}).decision == expected


def test_rules_can_escalate_but_not_downgrade() -> None:
    engine = DecisionEngine()
    result = engine.decide(0.1, {"impossible_travel": 1, "new_device": 1})
    assert result.decision == Decision.BLOCK
    assert "impossible_travel_with_new_device" in result.rule_reasons


def test_invalid_probability_is_rejected() -> None:
    with pytest.raises(ValueError):
        DecisionEngine().decide(1.1, {})
