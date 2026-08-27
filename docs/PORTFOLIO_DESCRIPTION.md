# Portfolio Descriptions

## GitHub description

Production-style real-time fraud detection with FastAPI, Redpanda, PostgreSQL, calibrated tree models,
MLflow, SHAP, drift monitoring, Next.js, Grafana, and Docker Compose.

## Portfolio website

I built an end-to-end payment fraud platform that scores synchronous API requests and streamed events,
computes leakage-safe behavioral features, persists idempotent decisions, and routes suspicious payments
to review or block workflows. A separate chronological training pipeline compares model and imbalance
strategies, calibrates probabilities, optimizes business thresholds, and tracks versions in MLflow.
Operations are covered by delayed labels, SHAP, drift monitoring, Next.js, Prometheus, and Grafana.

## LinkedIn project

Built a production-style fraud detection system around a calibrated Random Forest champion, Kafka-compatible
streaming, PostgreSQL, and FastAPI. The measured 249,992-row demo achieved 0.3363 PR-AUC and 0.9266
precision on an untouched temporal test set. I also implemented transactional-outbox reliability,
business-cost decision thresholds, alert-only SHAP, delayed-label monitoring, drift reports, MLflow,
Next.js, Grafana, Docker Compose, and automated tests. Recall (0.3108) is openly documented as the main
model improvement area.

## Technical summary

The platform shares one scoring orchestrator between HTTP and Redpanda consumers. PostgreSQL supplies
past-only features and atomically stores transaction, prediction, alert, and outbox records. The model
produces calibrated risk; independent rules produce APPROVE, MANUAL_REVIEW, or BLOCK. Five training
strategies are evaluated chronologically, and challenger promotion is gated rather than automatic.

## Recruiter-friendly summary

This project demonstrates that I can take an ML model beyond a notebook: design reliable data flow,
serve predictions, connect streaming and databases, measure the right imbalanced-class metrics, explain
decisions, monitor drift, package services, test behavior, and communicate limitations honestly.
