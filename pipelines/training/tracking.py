from __future__ import annotations

import os
from contextlib import AbstractContextManager, nullcontext
from pathlib import Path
from typing import Any, cast


class MlflowTracker:
    def __init__(self, tracking_uri: str, common_params: dict[str, object]) -> None:
        self.common_params = common_params
        self.mlflow: Any | None = None
        if os.getenv("MLFLOW_TRACKING_DISABLED", "false").lower() == "true":
            return
        try:
            import mlflow

            mlflow.set_tracking_uri(tracking_uri)
            mlflow.set_experiment("fraud-detection-model-comparison")
            self.mlflow = mlflow
        except Exception as exc:
            print(f"MLflow tracking unavailable; model artifacts remain local: {exc}")

    def parent_run(self, run_name: str) -> AbstractContextManager[Any]:
        if self.mlflow is None:
            return nullcontext()
        return cast(AbstractContextManager[Any], self.mlflow.start_run(run_name=run_name))

    def nested_run(
        self,
        run_name: str,
        params: dict[str, object],
        metrics: dict[str, float],
        tags: dict[str, str] | None = None,
    ) -> None:
        if self.mlflow is None:
            return
        with self.mlflow.start_run(run_name=run_name, nested=True):
            self.mlflow.log_params({**self.common_params, **params})
            self.mlflow.log_metrics(metrics)
            if tags:
                self.mlflow.set_tags(tags)

    def log_final(
        self,
        model: Any,
        input_example: Any,
        report_path: Path,
        artifact_path: Path,
        params: dict[str, object],
        metrics: dict[str, float],
        feature_contract: dict[str, object],
    ) -> str | None:
        if self.mlflow is None:
            return None
        import mlflow.sklearn
        from mlflow.models import infer_signature
        from mlflow.tracking import MlflowClient

        self.mlflow.log_params({**self.common_params, **params})
        self.mlflow.log_metrics(metrics)
        self.mlflow.log_artifact(str(report_path))
        self.mlflow.log_artifact(str(artifact_path), artifact_path="portable-artifact")
        self.mlflow.log_dict(feature_contract, "feature_contract.json")
        model_info = mlflow.sklearn.log_model(
            model,
            "model",
            registered_model_name="fraud-detector",
            input_example=input_example,
            signature=infer_signature(input_example, model.predict_proba(input_example)),
        )
        run = self.mlflow.active_run()
        if run is None:
            return None
        client = MlflowClient()
        versions = client.search_model_versions("name='fraud-detector'")
        matching = [version for version in versions if version.run_id == run.info.run_id]
        if not matching:
            return None
        registered = max(matching, key=lambda version: int(version.version))
        client.set_registered_model_alias("fraud-detector", "challenger", registered.version)
        self.mlflow.set_tags(
            {
                "registry_alias": "challenger",
                "automatic_production_promotion": "false",
                "model_uri": model_info.model_uri,
            }
        )
        return str(registered.version)
