# Phase 6 Core Acceptance Evidence

Verified locally on 2026-08-27 (Europe/Istanbul) with Docker Desktop. The final V1 release remains
conditional on publishing the benchmark matrix listed under Explicitly not claimed.

## Clean bootstrap

The acceptance stack used the isolated Compose project `fraud-phase6-clean`; the normal project volumes
were stopped and preserved. Temporary acceptance volumes were deleted before the final run.

```powershell
docker compose -p fraud-phase6-clean down --volumes --remove-orphans
docker compose -p fraud-phase6-clean up -d --build
docker compose -p fraud-phase6-clean ps -a
docker compose -p fraud-phase6-clean exec -T api alembic current
```

Observed result:

- Python and Next.js production images built successfully.
- Volume initialization completed as root, then runtime services ran with their configured non-root users.
- The public demo dataset was materialized and 20 Random Forest plus 20 XGBoost Optuna trials ran.
- MLflow registered `fraud-detector`; API loaded trained version `20260827080316-fd1c4fda7381` with
  review/block thresholds `0.15/0.40` and `bootstrap_model: false`.
- Alembic reached `0004_promotion_idempotency (head)` on an empty PostgreSQL database.
- API, dashboard, PostgreSQL, Redpanda and MLflow reported healthy; worker, explainer, simulator,
  drift/retraining workers, Prometheus and Grafana remained running.

## End-to-end runtime

The live simulator/worker path produced transactions, predictions and alerts. At the evidence snapshot,
PostgreSQL contained 1,159 transactions and predictions, 312 alerts, 174 stored SHAP explanations, one
analyst-confirmed fraud alert and one confirmed fraud label. Unpublished outbox count was zero.

`GET /health/ready` returned `{"status":"ready"}`. The Playwright analyst flow generated a deterministic
velocity alert, opened the Alerts view, selected Confirm fraud and verified the resulting API state.

## Automated checks

| Check | Result |
|---|---:|
| Ruff | Passed |
| strict mypy | Passed, 34 source files |
| Backend unit/contract | 33 passed |
| Testcontainers PostgreSQL/Redpanda | 2 passed |
| ESLint | Passed |
| TypeScript | Passed |
| Next.js production build | Passed |
| Playwright dashboard/analyst E2E | 2 passed |
| Compose config | Passed |

## Corrections made by the clean run

- Compose now builds the shared Python image once instead of exporting the same image for each service.
- A scoped `volume-init` service fixes ownership of new model/data volumes before non-root services start.
- API and worker no longer create production tables from ORM metadata; Alembic is the schema authority.
- `0001_initial` now declares its historical schema instead of importing the current ORM model, preventing
  later migrations from colliding on a new database.
- The frontend lock file includes Linux optional dependencies, so Docker `npm ci` is reproducible.

## Explicitly not claimed

The full 10/50/100-user API benchmark and 10/50/100-event/s streaming benchmark matrix has not been
published. The p95 under 100 ms value remains a target, not a measured result. `npm audit` currently
reports two high-severity dependency findings; remediation belongs to the Phase 7 supply-chain work.
