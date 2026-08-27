from __future__ import annotations

import argparse

from mlflow.tracking import MlflowClient


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicitly assign an MLflow model alias; training never promotes production."
    )
    parser.add_argument("--tracking-uri", default="http://localhost:5000")
    parser.add_argument("--model", default="fraud-detector")
    parser.add_argument("--alias", choices=["champion", "challenger"], required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument(
        "--confirm-champion",
        action="store_true",
        help="Required when changing the champion alias.",
    )
    args = parser.parse_args()

    if args.alias == "champion" and not args.confirm_champion:
        raise SystemExit("Refusing champion update without --confirm-champion")

    client = MlflowClient(tracking_uri=args.tracking_uri)
    version = client.get_model_version(args.model, args.version)
    if version.status != "READY":
        raise SystemExit(f"Model version {args.version} is not READY: {version.status}")
    client.set_registered_model_alias(args.model, args.alias, args.version)
    print(f"{args.model}@{args.alias} -> version {args.version} ({version.run_id})")


if __name__ == "__main__":
    main()
