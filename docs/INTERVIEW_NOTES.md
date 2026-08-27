# Interview Notes

## Thirty-second explanation

I built a real-time fraud platform rather than a notebook model. Transactions arrive through FastAPI or
Redpanda, point-in-time behavioral features are calculated from prior PostgreSQL history, a calibrated
Random Forest champion produces risk, and a separate policy chooses approve, review, or block. State and outgoing
events commit through a transactional outbox. MLflow tracks training, SHAP explains alerts, delayed
labels update performance, and Prometheus/Grafana plus the Next.js command center cover operations.

## Likely questions and concise answers

### Why was Random Forest selected?

It was not predetermined. I compared Logistic Regression, Random Forest, XGBoost, undersampling, and
SMOTE on a later selection window. Random Forest won by configured expected cost with PR-AUC as the
tie-breaker. On the untouched demo test it achieved 0.3363 PR-AUC and 0.9266 precision, but recall was
0.3108, which I present as a limitation.

### Why not optimize accuracy?

Fraud is rare, so predicting every transaction as legitimate can look accurate while detecting no fraud.
I use precision, recall, F1, PR-AUC, ROC-AUC, false-positive/negative rates, and business cost.

### Why PR-AUC?

It focuses on positive-class retrieval and precision when negatives dominate. ROC-AUC can remain
visually strong because true-negative volume is enormous. I still report both.

### How did you handle imbalance?

I compared class weighting, balanced tree sampling, random undersampling, and SMOTE. Resampling occurs
only inside the oldest training partition; applying it before the time split would contaminate
evaluation. The measured candidate table is stored in `artifacts/challenger_model_report.json`.

### How did you prevent leakage?

All data is time-sorted, rolling windows exclude the current row, preprocessing fits only on training,
and selection/calibration/threshold/test periods are separate. Target, fraud-scenario fields, outcomes,
and label-conditioned synthetic country/device features are excluded from the model schema.

### Why calibrate probability?

Decision thresholds and expected costs treat probabilities as risk estimates, not just rankings.
Sigmoid calibration is fitted on a dedicated later period using a frozen champion, so it does not refit
the model or use the threshold/test periods.

### How are thresholds chosen?

I search ordered review/block pairs. The objective charges missed fraud by amount, legitimate blocks by
friction cost, every review by investigation cost, and reviewed fraud by expected residual loss. It also
enforces a maximum review rate. The demo selected 0.15 and 0.40—not the arbitrary 0.50 default.

### Why separate prediction and decision?

Probability is a model claim; APPROVE/REVIEW/BLOCK is business policy. Separation lets risk teams adjust
capacity/cost or add an impossible-travel rule without retraining, and it makes each escalation auditable.

### Why Kafka/Redpanda?

It decouples ingestion, scoring, alerts, explanations, and future consumers; supports replay; and scales
via partitions and consumer groups. Redpanda gives Kafka semantics with a simpler local stack.

### What happens if Redpanda goes down?

Synchronous API decisions still persist. Their outbox rows remain unpublished and retry when the broker
returns. Simulator traffic cannot enter until Redpanda recovers. The database remains the source of truth.

### What happens if prediction goes down?

Readiness fails and the payment caller receives an error rather than an unrecorded decision. Streaming
messages remain uncommitted and replay. A real company would define a risk-based fallback—fail open for
small trusted payments, fail closed for high risk—but this project does not pretend that policy exists.

### How is idempotency implemented?

`transaction_id` is the database primary key. Existing predictions are returned on retry. Kafka offsets
commit only after the database commit, so a replay cannot create a second prediction or alert.

### How do delayed labels work?

`POST /transactions/{id}/label` upserts analyst/chargeback truth and emits `confirmed_labels.v1`.
Performance endpoints join labels with the model version that produced each prediction. Drift can be
calculated immediately; actual performance waits for labels.

### How do you monitor drift?

The model bundle stores reference amount, country, and probability distributions. A scheduled worker
computes PSI/KS for numeric values and Jensen–Shannon divergence for country, persists the report, and
logs a drift event. Drift triggers investigation/retraining, not automatic promotion.

### How do fraudsters change the problem?

They adapt to static rules, probe thresholds, and coordinate across accounts/devices. Production needs
fast rule iteration, graph/entity features, investigator feedback, adversarial monitoring, and segmented
models. Labels also arrive with selection bias because only investigated cases are confirmed quickly.

### How would retraining work?

Confirmed labels and recent events create a new chronological dataset. The pipeline trains a challenger
and checks schema, business cost, PR-AUC, recall, and latency. It registers the version but never promotes
automatically; an explicit operational decision changes the champion.

### How would you deploy on AWS or GCP?

Containerize on EKS/GKE, use MSK/Pub/Sub or managed Kafka, RDS/Cloud SQL, managed Redis/feature store,
object storage for artifacts, managed Prometheus, and a secrets manager. CI would run tests/migrations,
sign images, deploy a challenger/canary, and roll back on SLO or model gates.

### What changes at 100,000 transactions per second?

Partition Kafka by user/entity, use hundreds of partitions and scaled consumer groups, move rolling state
to a distributed online feature store, use distributed model serving with batching only where latency
allows, shard operational storage, send analytics to a columnar warehouse, enforce schemas, and operate
on Kubernetes with autoscaling, backpressure, multi-region failover, and end-to-end tracing. The local
project does not support that rate.
