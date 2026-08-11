from __future__ import annotations

from typing import Any

import pandas as pd

from fraud_detection.domain import RiskFactor

FRIENDLY_NAMES = {
    "amount_vs_user_average": "Amount compared with normal spending",
    "transactions_last_5m": "Transactions in the last five minutes",
    "new_country": "First transaction from this country",
    "new_device": "First transaction from this device",
    "impossible_travel": "Geographically impossible travel",
    "ip_changed": "IP address changed",
}


def reason_code_explanation(features: dict[str, float], limit: int = 5) -> list[RiskFactor]:
    weights = {
        "impossible_travel": features.get("impossible_travel", 0) * 2.0,
        "new_device": features.get("new_device", 0) * 0.8,
        "new_country": features.get("new_country", 0) * 0.7,
        "transactions_last_5m": min(features.get("transactions_last_5m", 0), 10) * 0.22,
        "amount_vs_user_average": min(features.get("amount_vs_user_average", 1), 15) * 0.12,
        "ip_changed": features.get("ip_changed", 0) * 0.3,
    }
    ranked = sorted(weights.items(), key=lambda item: abs(item[1]), reverse=True)
    return [
        RiskFactor(feature=FRIENDLY_NAMES.get(name, name), impact=round(impact, 4))
        for name, impact in ranked[:limit]
        if impact != 0
    ]


def shap_explanation(
    artifact: dict[str, Any], features: dict[str, float], limit: int = 5
) -> list[RiskFactor]:
    import shap

    columns = artifact["feature_columns"]
    background = artifact["background"]
    model = artifact["model"]
    current = pd.DataFrame([{name: features.get(name, 0.0) for name in columns}])
    explainer = shap.Explainer(
        lambda values: model.predict_proba(pd.DataFrame(values, columns=columns))[:, 1],
        background,
        algorithm="permutation",
    )
    explanation = explainer(current)
    values = explanation.values[0]
    ranked = sorted(zip(columns, values, strict=True), key=lambda item: abs(item[1]), reverse=True)
    return [
        RiskFactor(
            feature=FRIENDLY_NAMES.get(name, name),
            impact=round(float(impact), 6),
            direction="increases_risk" if impact >= 0 else "decreases_risk",
        )
        for name, impact in ranked[:limit]
    ]
