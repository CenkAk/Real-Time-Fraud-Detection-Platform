# Real-Time Fraud Detection Platform

A production-style portfolio system that turns payment events into calibrated fraud probabilities,
business decisions, alerts, delayed-label metrics, drift reports, and operational dashboards. This is
an engineered application—not a notebook classifier—and deliberately separates model risk from the
policy that approves, reviews, or blocks a payment.

## Why this project exists

Fraud detection is a useful intersection of machine learning, streaming, backend design, data
engineering, MLOps, and business decision-making. This repository demonstrates those disciplines in
one locally reproducible system while being honest about its synthetic data and single-machine scale.

```mermaid
flowchart LR
    S[Transaction simulator] -->|transactions.v1| K[Redpanda]
    A[FastAPI] --> O[(Transactional outbox)]
    K --> W[Fraud scoring worker]
    A --> F[Feature engine]
    W --> F
    F --> M[Calibrated champion]
    M --> D[Decision engine]
    D --> P[(PostgreSQL)]
    P --> O
    O -->|predictions / alerts| K
    K --> X[SHAP worker]
    P --> UI[Streamlit dashboard]
    A --> PR[Prometheus]
    W --> PR
    PR --> G[Grafana]
    T[Training pipeline] --> ML[MLflow registry]
```

## Implemented capabilities

- FastAPI scoring with strict Pydantic contracts, OpenAPI docs, health checks, idempotent transaction
  IDs, and a normalized SQLAlchemy/PostgreSQL data model.
- Redpanda topics for transactions, predictions, alerts, confirmed labels, and dead-letter events;
  manual offset commits and a transactional outbox prevent database/event divergence.
- Point-in-time amount, behavioral, velocity, novelty, IP, and geographic features. Every online
  history query excludes the current and future events.
- Logistic Regression, Random Forest, XGBoost, random undersampling, and SMOTE comparison with
  chronological splits, calibration, business-cost thresholding, MLflow tracking, and registry entry.
- Separate risk score and decision policy with configurable review/block thresholds and escalation
  rules for bursts, anomalous amounts, new devices, and impossible travel.
- Asynchronous SHAP explanations for alerts, a transparent reason-code fallback, delayed confirmed
  labels, PSI/KS/Jensen–Shannon drift checks, and champion/challenger promotion gates.
- Streamlit fraud-operations dashboard plus Prometheus/Grafana system telemetry.
- Alembic migrations, structured JSON logs, Docker Compose, pytest, Ruff, mypy configuration, and a
  real Locust workload.

## Measured demo model results

These values come from `artifacts/model_report.json`, generated locally on 2026-08-11. The demo used a
deterministic 249,992-row sample distributed across the full Fraud Detection Handbook timeline. The
latest 15% was untouched until final evaluation.

| Metric | Held-out result |
|---|---:|
| Champion | XGBoost |
| Precision | 0.9000 |
| Recall | 0.2769 |
| F1 | 0.4235 |
| PR-AUC | 0.3139 |
| ROC-AUC | 0.6471 |
| False-positive rate | 0.000269 |
| False-negative rate | 0.7231 |
| Review / block thresholds | 0.10 / 0.30 |

Accuracy is intentionally not a selection metric: a model predicting “legitimate” for nearly every
payment can have excellent accuracy and still miss the fraud class. The champion was selected by
validation-period expected business cost, with PR-AUC as a tie-breaker. The reported cost value is a
configured simulation objective, not claimed financial savings.

## Data and leakage controls

The core source is the open [Fraud Detection Handbook simulated dataset](https://fraud-detection-handbook.github.io/fraud-detection-handbook/Chapter_3_GettingStarted/SimulatedDataset.html).
It contains chronological customer/terminal/amount events and time-dependent fraud scenarios. The
download script records the observed archive SHA-256.

Deterministic enrichment adds operational fields needed by the live event contract. Country/device
takeover context is label-conditioned synthetic behavior and is therefore **excluded from model
features**; it is used only to exercise explicit online rules and dashboards. `TX_FRAUD_SCENARIO`, the
target, and future aggregates are never model inputs. See [MODELING.md](docs/MODELING.md).

## Run locally

### Docker Compose

Docker Desktop is required but was not available in the implementation environment, so the Compose
topology is implemented but not locally executed here.

```bash
cp .env.example .env
docker compose up --build
```

The first start downloads the public data, creates a distributed demo sample, trains/registers the
model, applies migrations, and starts the services. Cached named volumes make later starts faster.

| Service | URL |
|---|---|
| API | http://localhost:8000 |
| Swagger | http://localhost:8000/docs |
| Streamlit | http://localhost:8501 |
| MLflow | http://localhost:5000 |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |

Use `docker compose --profile full up --build` to expose Redpanda Console and run the full-dataset
training job. This is substantially heavier than the demo profile.

### Native development

```bash
python -m venv .venv
.venv/Scripts/pip install -e ".[ml,streaming,dashboard,dev]"
python -m scripts.bootstrap
uvicorn apps.api.main:app --reload
```

Run the worker, simulator, explainer, monitor, and dashboard in separate terminals. PostgreSQL and
Redpanda connection settings come from `.env`.

## API example

```bash
curl -X POST http://localhost:8000/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "transaction_id":"txn-123","user_id":"user-883","merchant_id":"merchant-124",
    "timestamp":"2026-08-10T18:43:21Z","amount":149.95,"currency":"USD",
    "merchant_category":"electronics","country":"US","device_id":"device-992",
    "ip_address":"192.0.2.10","channel":"web"
  }'
```

Important endpoints include `/transactions/{id}`, `/predictions/{id}`,
`/predictions/{id}/explanation`, `/alerts`, `/transactions/{id}/label`, `/model/info`,
`/analytics/model-performance`, `/health/ready`, and `/metrics`.

## Testing and benchmarks

```bash
python -m ruff check .
python -m pytest
locust -f locustfile.py --host http://localhost:8000
```

The current local suite passes 15 tests. No API load benchmark was run because Docker/PostgreSQL/
Redpanda were unavailable; latency and throughput remain **Not measured**. Never copy the target p95
under 100 ms into a CV as if it were a result.

## Repository map

```text
apps/                 API, worker, simulator, Streamlit dashboard
src/fraud_detection/ Shared domain, feature, model, decision, DB, streaming, monitoring code
pipelines/            Data preparation, training, evaluation, retraining
alembic/              Database migrations
configs/              Auditable policy/cost defaults
docker/               Prometheus and Grafana provisioning
tests/                Unit, API, ML, drift, and lifecycle tests
docs/                 Architecture, modeling, ADRs, interview and portfolio material
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Modeling and leakage](docs/MODELING.md)
- [Decision log](docs/DECISIONS.md)

## Limitations and future improvements

This is a local portfolio platform using synthetic data. It has no authentication, PCI controls,
real payment integration, Redis/online feature store, Kubernetes deployment, managed secrets, schema
registry, or measured high-throughput claim. The demo’s uniformly sampled timeline approximates
rolling activity; full-data training is required for authoritative velocity evaluation.
