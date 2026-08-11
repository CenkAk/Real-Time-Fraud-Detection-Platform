from pipelines.retraining.run import compare_reports


def test_challenger_is_never_automatically_promoted() -> None:
    champion = {
        "model_version": "v1",
        "test_expected_cost": 100,
        "test_metrics": {"pr_auc": 0.5, "recall": 0.7},
    }
    challenger = {
        "model_version": "v2",
        "test_expected_cost": 90,
        "test_metrics": {"pr_auc": 0.6, "recall": 0.8},
    }
    decision = compare_reports(champion, challenger)
    assert decision["promotion_recommended"] is True
    assert decision["automatic_promotion"] is False
