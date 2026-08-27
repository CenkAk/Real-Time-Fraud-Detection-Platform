# Architecture Decision Log

## ADR-001: FastAPI for the authorization boundary

FastAPI provides typed validation, generated OpenAPI, dependency injection, and strong Python ML
integration. A JVM/Go service could offer stricter latency behavior, but would add a cross-language model
boundary that does not improve this portfolio version.

## ADR-002: Redpanda with Kafka semantics

Kafka concepts—topics, keys, partitions, offsets, consumer groups, replay—are the learning goal.
Redpanda preserves that API while removing ZooKeeper and simplifying local Compose. Managed Kafka would
be the likely production replacement.

## ADR-003: PostgreSQL and transactional outbox

PostgreSQL offers transactions, constraints, indexing, JSON for flexible explanations, and mature
operations. The outbox commits state and publish intent together; direct “write DB then publish” would
lose events during the gap. Redis is intentionally deferred until traffic makes SQL feature queries the
bottleneck.

## ADR-004: Synchronous API plus asynchronous events

Payment callers need an immediate decision, so `POST /transactions` scores synchronously. Persistence,
analytics, explanations, monitoring, and downstream integration remain event-driven. A pure `202` flow
would model back-office screening better but not authorization.

## ADR-005: Compare interpretable and boosted models

Logistic Regression establishes an interpretable baseline; Random Forest tests bagged nonlinear trees;
XGBoost tests boosted interactions. The measured demo chose Random Forest by configured expected cost, not by
brand preference. The architecture continues to support a different future champion.

## ADR-006: Separate probability from decision

The model estimates risk; policy incorporates review capacity, customer friction, and hard rules. This
allows policy changes without retraining and makes escalations auditable.

## ADR-007: MLflow registry with manual promotion

Runs, metrics, artifacts, and versions belong outside the API. A challenger may be recommended only when
cost, PR-AUC, recall, and schema gates pass. Promotion remains explicit to avoid silently deploying a
statistically better but operationally unsafe model.

## ADR-008: Alert-only SHAP

SHAP on every approval would spend latency where explanations are rarely consumed. REVIEW/BLOCK alerts
are explained asynchronously, leaving authorization latency independent of explanation cost.
