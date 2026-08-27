# V1 Release Candidate Report

Core acceptance verified: 2026-08-27. Final release gate: conditional on the benchmark matrix.

## Delivered

The V1 platform implements synchronous FastAPI and streamed Redpanda ingestion, point-in-time
PostgreSQL features, calibrated risk scoring, separate APPROVE/MANUAL_REVIEW/BLOCK policy, atomic
transaction/prediction/alert/outbox persistence, asynchronous SHAP explanations, delayed analyst
labels, drift/performance-triggered challenger jobs, audited manual promotion, MLflow tracking and a
Next.js Fraud Command Center. Prometheus and Grafana provide local system telemetry.

Training compares Logistic Regression and imbalance baselines with 20-trial Optuna searches for Random
Forest and XGBoost. Candidate trials are nested MLflow runs; calibration, threshold selection and the
untouched temporal test remain separate. Registry updates never promote a model automatically.

## Verification evidence

- Clean-volume `docker compose -p fraud-phase6-clean up -d --build`: passed, including public-data
  bootstrap, 40 Optuna trials, model registration, Alembic `0004_promotion_idempotency` head and all
  application services.
- Runtime flow: simulator → Redpanda → worker → PostgreSQL produced transactions, predictions and
  alerts; the outbox drained to zero; the explainer stored SHAP payloads.
- Analyst flow: Playwright resolved an alert as FRAUD and atomically produced a confirmed fraud label.
- Backend: Ruff passed; strict mypy passed across 34 source files; 33 unit/contract tests passed.
- Infrastructure integration: 2 Testcontainers tests passed against real PostgreSQL 16 and Redpanda.
- Frontend: ESLint, TypeScript, production build and 2 Playwright E2E tests passed.

See `docs/PHASE6_ACCEPTANCE.md` for the commands and observed runtime evidence.

## Measured model result

The checked-in `artifacts/challenger_model_report.json` was generated from 249,992 public synthetic
events on 2026-08-26. The selected Random Forest achieved precision 0.9266, recall 0.3108, F1 0.4654,
PR-AUC 0.3363, ROC-AUC 0.6677, false-positive rate 0.000215 and false-negative rate 0.6892 on the
untouched temporal test. Review/block thresholds are 0.15/0.40. Configured expected cost is an
experimental objective, not claimed financial savings.

## Known limitations

- The dataset is synthetic and the sampled demo only approximates dense sequential velocity behavior.
- Recall remains the primary model limitation.
- The full 10/50/100-user and streaming benchmark matrix is not yet published; no measured latency or
  throughput claim is made.
- No authentication/RBAC, schema registry, Redis online feature store, distributed tracing, cloud
  deployment, managed secrets or PCI controls are included in V1.
- `npm audit` reports two high-severity dependency findings; they are recorded for the Phase 7
  supply-chain work and were not force-fixed during V1 verification.

## Run

Copy `.env.example` to `.env`, then run `docker compose up --build`. Open the Fraud Command Center on
port 8501, Swagger on 8000, MLflow on 5000, Prometheus on 9090 and Grafana on 3000.
