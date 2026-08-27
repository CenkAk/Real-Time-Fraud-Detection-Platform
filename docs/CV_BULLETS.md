# Verified CV Bullet Options

Use only bullets that fit the role. The metrics below come from the checked-in model report; no latency
or throughput figure is included because those were not measured.

- Engineered an end-to-end real-time fraud detection platform with FastAPI, Redpanda, PostgreSQL,
  Random Forest/XGBoost experimentation, MLflow, SHAP, Prometheus/Grafana, Next.js, and Docker Compose.
- Built leakage-safe chronological feature pipelines and compared five model/imbalance strategies on
  249,992 public synthetic payment events, selecting Random Forest through business-cost optimization.
- Achieved 0.3363 PR-AUC, 0.9266 precision, and 0.4654 F1 on an untouched temporal test partition while
  documenting the resulting 0.3108 recall trade-off.
- Designed a configurable APPROVE/REVIEW/BLOCK policy that optimized separate 0.15/0.40 review/block
  thresholds using missed-fraud, customer-friction, investigation, and review-capacity costs.
- Implemented idempotent Kafka consumers and a transactional outbox so predictions, alerts, and database
  state recover safely from retries and broker outages.
- Added alert-only SHAP explanations, delayed-label performance monitoring, PSI/KS/Jensen–Shannon drift
  reports, and gated champion/challenger retraining without automatic promotion.
