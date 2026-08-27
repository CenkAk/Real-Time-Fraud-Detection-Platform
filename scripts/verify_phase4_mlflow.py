from __future__ import annotations

import argparse
import json

from mlflow.tracking import MlflowClient


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tracking-uri", default="http://localhost:5000")
    parser.add_argument("--experiment", default="fraud-detection-model-comparison")
    parser.add_argument("--model", default="fraud-detector")
    args = parser.parse_args()

    client = MlflowClient(tracking_uri=args.tracking_uri)
    experiment = client.get_experiment_by_name(args.experiment)
    if experiment is None:
        raise RuntimeError(f"MLflow experiment not found: {args.experiment}")

    runs = client.search_runs(
        [experiment.experiment_id], order_by=["attributes.start_time DESC"], max_results=1000
    )
    parents = [
        run
        for run in runs
        if "mlflow.parentRunId" not in run.data.tags
        and run.data.tags.get("registry_alias") == "challenger"
    ]
    if not parents:
        raise RuntimeError("No completed Phase 4 challenger parent run found")
    parent = parents[0]
    children = [
        run for run in runs if run.data.tags.get("mlflow.parentRunId") == parent.info.run_id
    ]
    tuning_trials = [run for run in children if run.data.tags.get("run_type") == "tuning_trial"]
    candidates = [run for run in children if run.data.tags.get("run_type") == "candidate"]
    registered = client.get_registered_model(args.model)
    champion = registered.aliases.get("champion")
    challenger = registered.aliases.get("challenger")
    if champion is None:
        raise RuntimeError("champion alias is missing")
    if challenger is None:
        raise RuntimeError("challenger alias is missing")
    version = client.get_model_version(args.model, challenger)

    result = {
        "experiment_id": experiment.experiment_id,
        "parent_run_id": parent.info.run_id,
        "parent_status": parent.info.status,
        "nested_run_count": len(children),
        "tuning_trial_count": len(tuning_trials),
        "candidate_count": len(candidates),
        "aliases": registered.aliases,
        "champion_version": champion,
        "challenger_version": challenger,
        "challenger_run_id": version.run_id,
        "automatic_production_promotion": parent.data.tags.get(
            "automatic_production_promotion"
        ),
    }
    print(json.dumps(result, indent=2))

    if parent.info.status != "FINISHED":
        raise RuntimeError(f"Parent run status is {parent.info.status}")
    if len(tuning_trials) != 40:
        raise RuntimeError(f"Expected 40 tuning trials, found {len(tuning_trials)}")
    if len(candidates) < 5:
        raise RuntimeError(f"Expected at least 5 candidate runs, found {len(candidates)}")
    if version.run_id != parent.info.run_id:
        raise RuntimeError("challenger alias does not point at the Phase 4 parent run")
    if parent.data.tags.get("automatic_production_promotion") != "false":
        raise RuntimeError("automatic production promotion guard is missing")


if __name__ == "__main__":
    main()
