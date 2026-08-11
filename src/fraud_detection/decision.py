"""Business decision policy kept separate from model inference."""

from dataclasses import dataclass

from fraud_detection.domain import Decision


@dataclass(frozen=True)
class DecisionResult:
    decision: Decision
    risk_score: int
    rule_reasons: list[str]


@dataclass(frozen=True)
class DecisionEngine:
    review_threshold: float = 0.40
    block_threshold: float = 0.70
    velocity_review_count: int = 8
    amount_ratio_review: float = 8.0

    def decide(self, probability: float, features: dict[str, float]) -> DecisionResult:
        if not 0 <= probability <= 1:
            raise ValueError("probability must be between zero and one")
        score = round(probability * 100)
        decision = (
            Decision.BLOCK
            if probability >= self.block_threshold
            else Decision.MANUAL_REVIEW
            if probability >= self.review_threshold
            else Decision.APPROVE
        )
        reasons: list[str] = []
        if features.get("impossible_travel", 0) == 1:
            reasons.append("impossible_travel")
        if features.get("transactions_last_5m", 0) >= self.velocity_review_count:
            reasons.append("rapid_transaction_burst")
        if features.get("amount_vs_user_average", 0) >= self.amount_ratio_review:
            reasons.append("unusually_large_amount")
        if reasons and decision == Decision.APPROVE:
            decision = Decision.MANUAL_REVIEW
        if "impossible_travel" in reasons and features.get("new_device", 0) == 1:
            decision = Decision.BLOCK
            reasons.append("impossible_travel_with_new_device")
        return DecisionResult(decision=decision, risk_score=score, rule_reasons=reasons)
