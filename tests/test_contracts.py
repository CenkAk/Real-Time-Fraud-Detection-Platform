from fraud_detection.domain import ConfirmedLabel, Prediction, Transaction


def test_public_contracts_generate_closed_json_schemas() -> None:
    transaction = Transaction.model_json_schema()
    prediction = Prediction.model_json_schema()
    label = ConfirmedLabel.model_json_schema()
    assert set(transaction["required"]) >= {
        "transaction_id",
        "user_id",
        "merchant_id",
        "timestamp",
        "amount",
    }
    assert "fraud_probability" in prediction["properties"]
    assert "is_fraud" in label["properties"]
