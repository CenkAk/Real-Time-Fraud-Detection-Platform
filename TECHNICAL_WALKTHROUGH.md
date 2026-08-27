# Technical Walkthrough

This document teaches the implemented system from the moment a payment arrives to the moment it appears
in monitoring. It describes the verified V1 repository and its documented trade-offs.

## 1. A transaction enters the system

A caller sends the versioned `Transaction` contract from `src/fraud_detection/domain.py`. Pydantic
rejects unknown fields, naive timestamps, nonpositive amounts, invalid country/currency lengths, invalid
IP addresses, and unsupported channels. Labels are deliberately absent: a payment cannot bring its own
answer into inference.

There are two ingestion paths:

1. `POST /transactions` in `apps/api/main.py` serves authorization callers and returns a decision
   synchronously.
2. `apps/simulator/main.py` publishes events to `transactions.v1`; `apps/worker/main.py` consumes them.

Both paths call `score_and_persist()` in `src/fraud_detection/database.py`. That shared boundary is
important: HTTP and Kafka cannot silently implement different features or policies.

### Why FastAPI?

FastAPI gives Python-native typed contracts, OpenAPI/Swagger, dependency-injected database sessions, and
simple health/metrics endpoints. A production company might use Go/Java for tighter latency control and
host the Python model separately; this local project benefits more from one typed Python path.

### Why Redpanda?

Redpanda exposes Kafka producer/consumer semantics without ZooKeeper. `transactions.v1` is the input;
`fraud_predictions.v1` and `fraud_alerts.v1` are outputs. Kafka creates replayable, independently
scalable boundaries. It does not itself guarantee exactly-once business effects, so the code also uses
database idempotency and an outbox.

## 2. Point-in-time history and feature generation

`SQLHistoryProvider.prior_transactions()` queries the `(user_id, timestamp)` index for the previous 30
days, explicitly requiring `history.timestamp < current.timestamp`. SQLite tests and the in-memory
provider obey the same contract.

`calculate_features()` in `src/fraud_detection/features.py` receives the current `Transaction` plus a
sequence of earlier transactions and returns `FeatureVector(values: dict[str, float])`.

Important logic:

- It filters and sorts history again. This defensive check means a buggy provider still cannot include
  a future event.
- Local `recent(window)` calls calculate 1m, 5m, 1h, and 24h counts.
- Prior amounts produce mean, median, amount deviation, and hourly amount.
- Sets of historical merchant, country, and device IDs produce novelty flags.
- The latest previous location and elapsed time pass through `_haversine_km()` to estimate travel speed;
  speed above 900 km/h becomes `impossible_travel`.
- Empty history uses neutral amount baselines and does not mark every first payment as a novelty risk.

Without this function the model would see only the current amount and lose the behavioral context that
makes fraud detection meaningful. The local weakness is that fetching and calculating a user’s recent
history for every payment is database/CPU work. Production would atomically update precomputed online
aggregates in Redis, Flink, or a managed feature store.

### Offline/online consistency

`pipelines/training/data.py` implements batch point-in-time transformations. Rolling windows use
`closed="left"`, and expanding amount statistics shift one row. `tests/test_features.py` deliberately
passes a future high-value payment and proves it cannot change the current feature vector.

The demo’s uniformly distributed 249,992-row sample makes user histories sparse; it is suitable for a
resource-conscious demonstration but only approximates velocity. The full profile processes every row.

## 3. Model inference

`load_model()` in `src/fraud_detection/model.py` reads the joblib bundle. The bundle contains:

- calibrated scikit-learn-compatible model;
- version and exact feature order;
- optimized review/block thresholds;
- SHAP background sample;
- reference amount, country, and probability distributions.

`SklearnModel.predict_probability()` sends a named one-row structure through `predict_proba()` and
returns the positive-class probability. The wrapper keeps scikit-learn details out of the service.

If no artifact exists, `HeuristicBootstrapModel` makes local endpoints demonstrable and
`/model/info` exposes `bootstrap_model: true`. It is not the trained model and must never be used for CV
metrics. Compose runs the bootstrap training before the API starts, so the normal container path loads
the champion.

`ScoringService.score()` in `src/fraud_detection/service.py` times the sequence:

1. request prior history;
2. calculate features;
3. predict probability;
4. decide policy;
5. build the versioned `Prediction` response.

The model’s job ends at probability. It does not write databases, call Kafka, or choose business action.

## 4. Risk score and decision engine

`DecisionEngine.decide()` converts probability to `round(probability * 100)` and applies ordered
thresholds. The trained bundle currently supplies review `0.15` and block `0.40`; environment policy can
explicitly override model thresholds.

Rules then inspect features:

- at least eight transactions in five minutes → rapid burst reason;
- amount at least eight times the prior average → unusually large reason;
- impossible travel → travel reason;
- impossible travel plus a new device → BLOCK;
- other reasons can escalate APPROVE to MANUAL_REVIEW;
- rules never downgrade a model decision.

This separation is a central design choice. A calibrated probability is a statistical estimate; review
capacity and customer friction are business constraints. Risk teams can change policy without retraining
the estimator. `tests/test_decision.py` covers exact threshold boundaries, escalation, and invalid
probabilities.

## 5. Atomic persistence and event publication

`score_and_persist()` first checks `predictions.transaction_id`. If a caller retries, it returns the
existing prediction. For a new payment it stages user, merchant, transaction, prediction, optional alert,
and outbox rows in one SQL transaction.

The key pattern is the transactional outbox:

```text
database transaction
  ├─ transaction
  ├─ prediction
  ├─ optional alert
  └─ publish intents
        ├─ transactions.v1
        ├─ fraud_predictions.v1
        └─ fraud_alerts.v1
```

`publish_outbox_batch()` locks unpublished rows, publishes JSON with an idempotent producer, and marks
them published. A crash after Kafka accepts an event but before `published_at` commits can duplicate the
event. That is why consumers key/idempotency by transaction ID. “Exactly once” is achieved at the
business-effect level, not assumed from a broker slogan.

The worker disables automatic commits. It commits a Kafka offset only after PostgreSQL commits. Invalid
events are published to `transactions.dlq.v1` with the original payload and error, then committed so a
poison message cannot stop a partition forever.

## 6. Alerts and explainability

REVIEW and BLOCK create `FraudAlertRecord`. The immediate response contains cheap rule reason codes; it
does not calculate SHAP on the authorization thread.

`apps/worker/explainer.py` consumes `fraud_alerts.v1`, reconstructs the transaction’s point-in-time
features, and calls `shap_explanation()` in `src/fraud_detection/explainability.py`. The packaged
background and permutation explainer produce signed impacts, which are converted into human-readable
risk factors and stored on the alert. If no trained artifact exists, `reason_code_explanation()` gives a
transparent fallback.

`GET /predictions/{id}/explanation` returns `pending` until this completes. Explanation failure cannot
delay or reverse authorization. At high volume, SHAP workers would autoscale separately, cap workloads,
and likely use model-specific TreeSHAP for a tree champion.

## 7. Dashboard and system monitoring

`apps/web` is a Next.js/TypeScript API client and BFF; it does not bypass service contracts to query
PostgreSQL. The Fraud Command Center displays 24-hour volume, decision counts, risk distribution,
alerts, transaction/prediction details, explanation status, model lifecycle and active thresholds.

`src/fraud_detection/observability.py` defines Prometheus counters/histograms. The API exposes `/metrics`;
worker processes expose ports 9101/9102. Prometheus scrapes them and the provisioned Grafana dashboard
shows decision rates, p95 inference latency, and errors. Structured JSON logs use transaction, request,
and model identifiers where available.

The Locust task in `locustfile.py` sends unique valid payments. It is real executable load code, but it
was not run in this environment. Average/p50/p95/p99 latency and throughput remain **Not measured**.

## 8. Delayed labels and model performance

Fraud truth commonly arrives as a chargeback or analyst decision. It is not present during authorization.
`POST /transactions/{id}/label` upserts `ConfirmedLabelRecord` and writes `confirmed_labels.v1` to the
outbox. `/analytics/model-performance` joins these labels with their original predictions and returns
precision, recall, and F1 only when labels exist.

This avoids pretending unlabeled recent approvals are genuine. A production metric service would also
account for label maturity windows, investigation selection bias, late chargebacks, and per-segment
confidence intervals.

## 9. Drift monitoring

`apps/worker/monitor.py` runs every five minutes and waits for at least 100 recent transactions. It
compares the last day with model-bundle references:

- amount and fraud probability: Population Stability Index plus Kolmogorov–Smirnov statistic/p-value;
- country: Jensen–Shannon divergence.

A PSI of 0.20 or country JS of 0.10 sets `drift_detected`. The report is persisted with model version and
window boundaries. Drift is evidence that input/ranking behavior changed; it is not proof that accuracy
fell. Delayed labels are required to distinguish data drift from concept/performance drift.

## 10. How training works

`scripts/bootstrap.py` is idempotent. It downloads the public dataset if missing, writes a SHA-256
manifest, cleans zero-value simulator rows, distributes a demo sample across the full timeline,
materializes features, and calls `train()`.

### Classification and probability

Binary classification learns a mapping from transaction features to fraud/nonfraud. `predict_proba()`
returns a ranking/risk value, not certainty. Calibration maps raw model scores toward observed event
rates so cost thresholds are more meaningful.

### Temporal partitions

`chronological_slices()` creates:

- 50% training;
- 15% candidate selection;
- 10% calibration;
- 10% threshold optimization;
- 15% untouched test.

Random splitting would let older training learn from customer/merchant behavior that occurred later in
real time. Keeping the final period untouched gives a more honest deployment simulation.

### Imbalance experiments

`candidate_models()` creates class-weighted Logistic Regression, balanced Random Forest, weighted
XGBoost, undersampled Logistic Regression, and SMOTE Logistic Regression. Only training data is resampled.
SMOTE before splitting would synthesize points using future/test neighbors and leak information.

### Metrics in this project

- **Precision:** among blocks, how many were fraud. Test: 0.9266. High precision limits customer harm.
- **Recall:** among frauds, how many were blocked. Test: 0.3108. This value exposes missed-fraud risk.
- **F1:** harmonic mean of precision and recall. Test: 0.4654.
- **PR-AUC:** precision/recall performance over all thresholds. Test: 0.3363; useful for rare fraud.
- **ROC-AUC:** ranking of positive above negative across thresholds. Test: 0.6677; reported but not primary.
- **False-positive rate:** legitimate transactions incorrectly blocked divided by all legitimate events.
- **False-negative rate:** fraud not blocked divided by all fraud; test 0.6892.
- **Confusion matrix:** counts of true/false positives/negatives at a threshold. The component rates are
  in the report; adding a stored plotted matrix is a sensible presentation improvement.

### Business cost and threshold tuning

`expected_cost()` charges approved fraud by amount, review by fixed investigation cost plus residual
fraud loss after an assumed catch rate, and legitimate block by friction cost. `optimize_thresholds()`
searches two ordered thresholds and rejects policies exceeding 5% review capacity. It selected 0.15/
0.40 on a separate threshold period. These cost units demonstrate decision methodology; they are not
claimed dollars prevented.

### Champion packaging and MLflow

The lowest-cost candidate wins, with PR-AUC as tie-breaker. The measured demo selected Random Forest. The champion is
refit through the selection boundary, frozen, sigmoid-calibrated, and evaluated once on test. Joblib and
MLflow store the model, metrics, report, feature contract, references, and thresholds. The registered
name is `fraud-detector`.

## 11. Retraining and safe promotion

`pipelines/retraining/run.py` trains `challenger.joblib`, reads the champion report, and checks:

- PR-AUC does not decline by more than 0.01;
- recall does not decline by more than 0.02;
- expected test cost does not increase.

It writes `promotion_recommended` plus `automatic_promotion: false`. This intentionally stops a new model
from silently becoming production champion. A real approval would also require latency, calibration,
segment fairness, model-risk review, and canary monitoring.

## 12. Complete example: a $1,250 payment

Assume `user-883` usually spends about $100 and recently changed device/location.

1. `TransactionSimulator.next()` or an API caller constructs the event.
2. `publish_json()` places it on `transactions.v1`, or FastAPI calls persistence directly.
3. `worker.run()` validates `Transaction` and opens a SQL session.
4. `SQLHistoryProvider.prior_transactions()` returns only earlier user events.
5. `calculate_features()` might produce amount ratio 12.5, new device 1, and impossible travel 1.
6. `SklearnModel.predict_probability()` could return 0.91. This value is illustrative—not a measured
   prediction for a stored transaction.
7. `DecisionEngine.decide()` returns risk score 91 and BLOCK; impossible travel/new device also supplies
   an auditable escalation reason.
8. `score_and_persist()` atomically inserts transaction, prediction, alert, and outbox rows.
9. `publish_outbox_batch()` emits prediction and alert events.
10. The explainer consumes the alert and stores top SHAP factors.
11. The Next.js Fraud Command Center reads `/alerts`, `/transactions/{id}`, `/predictions/{id}`, and its explanation.
12. Prometheus/Grafana observe counts and latency; a later confirmed label updates model performance.

The 0.91 value is intentionally presented as a flow example, not a fabricated benchmark.

## 13. Docker and configuration

The multi-stage-looking single runtime `Dockerfile` installs all service extras and runs as UID 10001.
Compose supplies PostgreSQL, Redpanda, MLflow, bootstrap, API, workers, simulator, dashboard, Prometheus,
and Grafana. Named volumes persist data/artifacts. Health-based dependencies prevent the API from loading
before migration/bootstrap dependencies are ready.

`.env.example` holds local defaults; secrets are not committed. Environment variables override database,
broker, artifact, thresholds, costs, simulator, and dashboard settings. Production would use a secrets
manager and separate service identities, not shared local credentials.

The 2026-08-27 V1 acceptance run verified both production image builds and a clean-volume Compose
bootstrap through training, registration, migrations, healthy services and the analyst label flow.

## 14. How this would work at Stripe-scale

### Around 100 transactions/second

The conceptual topology can remain. Add several Kafka partitions keyed by user, multiple API/worker
replicas, connection pooling, Redis for hot rolling features, and strict latency/error SLOs. PostgreSQL
may remain primary with read replicas and partitioned tables.

### Around 1,000 transactions/second

Run Kubernetes, autoscale stateless inference, use dozens of partitions, isolate outbox publishing,
precompute features in a stream processor, cache model artifacts locally, and separate alert analytics
from the transactional database. Adopt schema registry compatibility and distributed tracing.

### Around 10,000 transactions/second

Use a dedicated online feature store with event-time correctness, sharded/partitioned operational stores,
distributed model serving, per-region Kafka, backpressure, load shedding, circuit breakers, and automated
canary models. Offline and online features must be generated from shared declarative definitions.

### 100,000+ transactions/second

Use hundreds/thousands of partitions based on measured throughput, regional ingestion and model-serving
cells, multi-region fault isolation, replicated entity state, globally coordinated model/config rollout,
columnar lakehouse analytics, continuous label pipelines, specialized graph-risk services, and mature
on-call/SLO/error-budget practice. Kubernetes autoscaling alone is not sufficient; storage, feature
consistency, network, failover, observability cardinality, and operational governance become primary
architecture problems.

The implemented local system supports none of these throughput claims. It demonstrates the component
boundaries and correctness patterns from which a scaled system can be discussed.

## 15. What to improve next

Publish the complete Locust/streaming p50/p95/p99 benchmark matrix, train the full sequential dataset,
improve recall through terminal/entity encodings and graph features, add explicit model calibration plots
and confusion-matrix artifacts, protect APIs with authentication, and deploy a canary in managed cloud
infrastructure.
