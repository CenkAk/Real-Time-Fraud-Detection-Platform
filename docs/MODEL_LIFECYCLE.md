# Model Monitoring and Retraining Lifecycle

Analyst resolutions are delayed ground-truth labels. They are persisted atomically with the alert
resolution and published to `confirmed_labels.v1`. A label changes monitoring evidence immediately;
it does not mutate the running model or promote a new model.

## Triggers

- Drift: PSI `>= 0.20` or Jensen-Shannon divergence `>= 0.10` in two consecutive windows.
- Performance: at least 200 confirmed labels and either a relative PR-AUC drop of `>= 10%` or an
  expected-cost increase of `>= 15%` against the champion test report.
- Manual: `POST /admin/retraining-jobs` with a named requester and reason.

Amount, velocity, country, merchant category, channel, and fraud probability are monitored. Reports
are stored for the overall population and country/category/channel segments. Calibration (Brier score)
and mean label delay are reported separately from trigger metrics.

## Challenger and promotion

Triggers only create an idempotent queued job. The retraining worker runs the temporal training
pipeline, registers a challenger in MLflow, and applies the PR-AUC, recall, and business-cost gates.
Even a passing challenger remains inactive. Promotion requires an explicit API request, updates the
MLflow `champion` alias, the `model_versions` stage, and an immutable `model_promotions` record. A
database failure restores the previous MLflow alias.

The active API process does not hot-reload a promoted artifact. A controlled service restart/model
reload is still required; this limitation prevents an uncoordinated partial rollout.
