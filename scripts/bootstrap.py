"""Idempotently prepare demo data and train the initial champion model."""

from pathlib import Path

from pipelines.training.data import (
    clean_source,
    download_dataset,
    enrich,
    load_public_data,
    materialize_features,
    validate_source,
)
from pipelines.training.train import train


def main() -> None:
    data_path = Path("data/processed/features.parquet")
    artifact_path = Path("artifacts/models/champion.joblib")
    if not data_path.exists():
        archive = download_dataset(Path("data/raw"))
        frame = load_public_data(archive, maximum_rows=250_000)
        validate_source(frame)
        data_path.parent.mkdir(parents=True, exist_ok=True)
        materialize_features(enrich(clean_source(frame))).to_parquet(data_path, index=False)
    if not artifact_path.exists():
        train(data_path, artifact_path, Path("artifacts/model_report.json"))


if __name__ == "__main__":
    main()
