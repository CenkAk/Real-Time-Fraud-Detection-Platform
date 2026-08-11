from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from pipelines.training.train import train


def compare_reports(
    champion: dict[str, object], challenger: dict[str, object]
) -> dict[str, object]:
    current = champion["test_metrics"]
    candidate = challenger["test_metrics"]
    assert isinstance(current, dict) and isinstance(candidate, dict)

    def numeric(mapping: dict[object, object], key: str) -> float:
        value = mapping[key]
        if not isinstance(value, (int, float)):
            raise TypeError(f"{key} must be numeric")
        return float(value)

    champion_cost = champion["test_expected_cost"]
    challenger_cost = challenger["test_expected_cost"]
    if not isinstance(champion_cost, (int, float)) or not isinstance(challenger_cost, (int, float)):
        raise TypeError("test_expected_cost must be numeric")
    gates = {
        "pr_auc": numeric(candidate, "pr_auc") >= numeric(current, "pr_auc") - 0.01,
        "recall": numeric(candidate, "recall") >= numeric(current, "recall") - 0.02,
        "business_cost": float(challenger_cost) <= float(champion_cost),
    }
    return {
        "evaluated_at": datetime.now(UTC).isoformat(),
        "promotion_recommended": all(gates.values()),
        "automatic_promotion": False,
        "gates": gates,
        "champion_version": champion["model_version"],
        "challenger_version": challenger["model_version"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/processed/features.parquet"))
    parser.add_argument("--champion-report", type=Path, default=Path("artifacts/model_report.json"))
    parser.add_argument(
        "--challenger", type=Path, default=Path("artifacts/models/challenger.joblib")
    )
    args = parser.parse_args()
    champion = json.loads(args.champion_report.read_text(encoding="utf-8"))
    challenger_report_path = Path("artifacts/challenger_report.json")
    challenger = train(args.data, args.challenger, challenger_report_path)
    decision = compare_reports(champion, challenger)
    Path("artifacts/promotion_decision.json").write_text(
        json.dumps(decision, indent=2), encoding="utf-8"
    )
    print(json.dumps(decision, indent=2))


if __name__ == "__main__":
    main()
