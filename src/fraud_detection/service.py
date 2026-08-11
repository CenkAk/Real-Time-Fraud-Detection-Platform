"""Shared synchronous scoring orchestration."""

from dataclasses import dataclass
from time import perf_counter

from fraud_detection.decision import DecisionEngine
from fraud_detection.domain import Prediction, Transaction
from fraud_detection.features import HistoryProvider, calculate_features
from fraud_detection.model import ProbabilityModel


@dataclass(frozen=True)
class ScoringResult:
    """Prediction plus the immutable point-in-time inputs that produced it."""

    prediction: Prediction
    feature_snapshot: dict[str, float]


class ScoringService:
    def __init__(
        self,
        history: HistoryProvider,
        model: ProbabilityModel,
        decision_engine: DecisionEngine,
    ) -> None:
        self.history = history
        self.model = model
        self.decision_engine = decision_engine

    def score(self, transaction: Transaction) -> Prediction:
        return self.score_with_features(transaction).prediction

    def score_with_features(self, transaction: Transaction) -> ScoringResult:
        started = perf_counter()
        history = self.history.prior_transactions(transaction, days=30)
        features = calculate_features(transaction, history).values
        probability = self.model.predict_probability(features)
        decision = self.decision_engine.decide(probability, features)
        return ScoringResult(
            prediction=Prediction(
                transaction_id=transaction.transaction_id,
                fraud_probability=probability,
                risk_score=decision.risk_score,
                decision=decision.decision,
                model_version=self.model.version,
                processing_time_ms=(perf_counter() - started) * 1000,
                rule_reasons=decision.rule_reasons,
            ),
            feature_snapshot=features,
        )
