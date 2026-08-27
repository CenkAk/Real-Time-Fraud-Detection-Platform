# V1 Release Checklist

Status: core acceptance verified locally on 2026-08-27; final V1 release is conditional.

- [x] Clean named-volume Compose bootstrap builds both production images.
- [x] Public data preparation, 40 Optuna trials, MLflow tracking and registry creation complete.
- [x] Empty PostgreSQL migrates through Alembic head.
- [x] Simulator → Redpanda → worker → model → PostgreSQL path produces one durable decision per ID.
- [x] APPROVE, MANUAL_REVIEW and BLOCK decisions are observable.
- [x] Alerts receive asynchronous SHAP explanations.
- [x] Analyst fraud/legitimate resolution writes delayed labels atomically.
- [x] Outbox drains without pending rows during healthy operation.
- [x] Drift/performance reports, retraining jobs and explicit promotion controls are exposed.
- [x] Next.js dashboard, API, MLflow, Prometheus and Grafana are reachable.
- [x] Ruff, strict mypy and 33 backend unit/contract tests pass.
- [x] Two real PostgreSQL/Redpanda Testcontainers integration tests pass.
- [x] ESLint, TypeScript, Next.js build and two Playwright E2E tests pass.
- [x] README, reports, walkthroughs, CV and portfolio text use measured Random Forest results.
- [x] No benchmark, fraud-prevention or financial-savings claim is presented as measured.
- [ ] Publish the required three-run 10/50/100-user API and 10/50/100-event/s streaming benchmark matrix.

Known release notes:

- The comprehensive performance benchmark remains the only open V1 evidence gate; see `BENCHMARKS.md`.
- `npm audit` reports two high-severity dependency findings queued for Phase 7.
- V1 intentionally excludes OIDC/RBAC, Redis, schema registry, tracing and cloud deployment.
