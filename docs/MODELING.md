# Modeling and Leakage Controls

## Dataset

The public Fraud Detection Handbook simulator provides 183 days of chronological customer, terminal,
amount, and fraud-label data. The demo distributes 249,992 selected rows across the full time range;
the full profile processes all rows. Zero-value simulator artifacts are counted out by the cleaning
step because the live payment schema requires `amount > 0`.

Deterministic enrichment produces API-compatible merchant categories, countries, channels, devices,
and IPs. Fraud rows receive takeover-style device/country context to exercise rules. Because that
context is generated from the label, `new_country` and `new_device` are explicitly excluded from
`FEATURE_COLUMNS` and never contribute to reported model metrics.

## Point-in-time features

Model inputs are amount, hour, weekday, prior user mean/median amount, amount-to-mean ratio, prior 5m/
1h/24h counts, and new-merchant status. The live feature engine additionally calculates 1m counts,
hourly amount, unique merchants/countries, country/device/IP novelty, travel speed, and impossible
travel for rules and monitoring.

Every rolling calculation is closed on the left or filters `timestamp < current.timestamp`. The target,
fraud scenario, post-transaction outcome, current row in rolling aggregates, and all future events are
forbidden.

## Temporal evaluation

Sorted data is divided into 50% training, 15% model selection, 10% calibration, 10% threshold tuning,
and 15% final test. Candidate selection and calibration cannot see the final test. This imitates
deployment into later behavior and avoids optimistic random mixing.

## Imbalance and candidates

The pipeline compares class-weighted Logistic Regression, balanced Random Forest, weighted XGBoost,
random undersampling, and SMOTE. Sampling occurs only in the training partition. Accuracy is excluded
from optimization. PR-AUC describes performance on the rare positive class more directly than ROC-AUC.

The measured demo selected XGBoost by expected cost. Test precision was 0.9000, recall 0.2769, F1
0.4235, PR-AUC 0.3139, and ROC-AUC 0.6471. High precision with low recall is a real trade-off and a
clear improvement target, not something hidden behind accuracy.

## Calibration and thresholds

The fitted champion is frozen and sigmoid-calibrated on its dedicated period. Threshold search uses:

- missed approved fraud: transaction amount;
- reviewed fraud: residual amount after configured 80% review catch rate;
- every review: 5 cost units;
- legitimate block: 25 friction units;
- maximum review queue: 5% of traffic.

Grid search produced review `0.10` and block `0.30` on the threshold partition. These values are packaged
with the model and used by deployment unless configuration explicitly disables model thresholds. Cost
units are an experiment objective, not real currency saved.

## Explainability and drift

The artifact stores a 200-row background for alert-only permutation SHAP. Friendly names and signed
impacts are persisted with the alert. Drift reference samples cover amount, country, and fraud
probability. Monitoring applies PSI and KS to numeric distributions and Jensen–Shannon divergence to
country. Thresholds are operational signals, not proof of concept drift; confirmed-label degradation is
also needed.

## Limitations

Synthetic behavior is simpler than adversarial production fraud. The demo’s distributed sampling makes
history sparse and therefore approximates velocity; use the full profile for better sequential fidelity.
No hyperparameter search beyond explicit candidate configurations has yet been measured. Labels are
simulated, and probability calibration may shift on real payment populations.

