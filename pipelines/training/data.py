from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

DATASET_URL = (
    "https://github.com/Fraud-Detection-Handbook/simulated-data-raw/archive/refs/heads/main.zip"
)
COUNTRIES = ["US", "GB", "TR", "DE", "FR"]
CATEGORIES = ["grocery", "travel", "electronics", "fuel", "restaurant", "entertainment"]


def download_dataset(destination: Path, url: str = DATASET_URL) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "fraud-handbook-main.zip"
    if not archive.exists():
        urllib.request.urlretrieve(url, archive)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    (destination / "download_manifest.json").write_text(
        json.dumps({"url": url, "sha256": digest}, indent=2), encoding="utf-8"
    )
    return archive


def load_public_data(archive: Path, maximum_rows: int | None = None) -> pd.DataFrame:
    extract_dir = archive.parent / "extracted"
    if not extract_dir.exists():
        with zipfile.ZipFile(archive) as bundle:
            bundle.extractall(extract_dir)
    files = sorted(extract_dir.rglob("*.pkl"))
    if not files:
        raise FileNotFoundError("no daily pickle files found in dataset archive")
    frames: list[pd.DataFrame] = []
    for file in files:
        frame = pd.read_pickle(file)
        frames.append(frame)
    result = pd.concat(frames, ignore_index=True).sort_values("TX_DATETIME")
    if maximum_rows is not None and len(result) > maximum_rows:
        positions = np.linspace(0, len(result) - 1, maximum_rows, dtype=int)
        return result.iloc[positions].copy()
    return result


def validate_source(frame: pd.DataFrame) -> None:
    required = {
        "TRANSACTION_ID",
        "TX_DATETIME",
        "CUSTOMER_ID",
        "TERMINAL_ID",
        "TX_AMOUNT",
        "TX_FRAUD",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"dataset is missing columns: {sorted(missing)}")
    if frame["TRANSACTION_ID"].duplicated().any():
        raise ValueError("transaction identifiers are not unique")
    if (frame["TX_AMOUNT"] < 0).any():
        raise ValueError("transaction amounts cannot be negative")
    if not frame["TX_FRAUD"].isin([0, 1]).all():
        raise ValueError("fraud target must be binary")


def clean_source(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.loc[frame["TX_AMOUNT"] > 0].copy()


def enrich(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.rename(
        columns={
            "TRANSACTION_ID": "transaction_id",
            "TX_DATETIME": "timestamp",
            "CUSTOMER_ID": "user_id",
            "TERMINAL_ID": "merchant_id",
            "TX_AMOUNT": "amount",
            "TX_FRAUD": "is_fraud",
        }
    ).copy()
    result["user_id"] = result["user_id"].map(lambda value: f"user-{int(value):05d}")
    result["merchant_id"] = result["merchant_id"].map(lambda value: f"merchant-{int(value):05d}")
    user_number = result["user_id"].str.split("-").str[-1].astype(int)
    merchant_number = result["merchant_id"].str.split("-").str[-1].astype(int)
    result["merchant_category"] = merchant_number.map(
        lambda value: CATEGORIES[value % len(CATEGORIES)]
    )
    result["country"] = user_number.map(lambda value: COUNTRIES[value % len(COUNTRIES)])
    result["device_id"] = user_number.map(lambda value: f"device-{value:05d}")
    result["ip_address"] = user_number.map(lambda value: f"192.0.2.{value % 253 + 1}")
    result["channel"] = merchant_number.map(lambda value: ["web", "mobile", "pos"][value % 3])
    fraud_mask = result["is_fraud"].astype(bool)
    result.loc[fraud_mask, "country"] = user_number[fraud_mask].map(
        lambda value: COUNTRIES[(value + 2) % len(COUNTRIES)]
    )
    result.loc[fraud_mask, "device_id"] = result.loc[fraud_mask, "transaction_id"].map(
        lambda value: f"takeover-{value}"
    )
    return result


def materialize_features(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.sort_values("timestamp").copy()
    grouped = frame.groupby("user_id", sort=False)
    frame["user_average_amount"] = grouped["amount"].transform(
        lambda values: values.expanding().mean().shift(1)
    )
    frame["user_median_amount"] = grouped["amount"].transform(
        lambda values: values.expanding().median().shift(1)
    )
    frame["user_average_amount"] = frame["user_average_amount"].fillna(frame["amount"])
    frame["user_median_amount"] = frame["user_median_amount"].fillna(frame["amount"])
    frame["amount_vs_user_average"] = frame["amount"] / frame["user_average_amount"].clip(
        lower=0.01
    )
    frame["hour"] = pd.to_datetime(frame["timestamp"]).dt.hour
    frame["weekday"] = pd.to_datetime(frame["timestamp"]).dt.weekday
    frame["new_merchant"] = (~frame.duplicated(["user_id", "merchant_id"])).astype(int)
    frame["new_country"] = (~frame.duplicated(["user_id", "country"])).astype(int)
    frame["new_device"] = (~frame.duplicated(["user_id", "device_id"])).astype(int)
    frame[["new_merchant", "new_country", "new_device"]] = frame[
        ["new_merchant", "new_country", "new_device"]
    ].where(grouped.cumcount() > 0, 0)

    frame["_row_id"] = range(len(frame))
    ordered = frame.sort_values(["user_id", "timestamp"]).copy()
    indexed = ordered.set_index("timestamp")
    for name, window in (
        ("transactions_last_5m", "5min"),
        ("transactions_last_1h", "1h"),
        ("transactions_last_24h", "24h"),
    ):
        values = (
            indexed.groupby("user_id")["amount"].rolling(window, closed="left").count().to_numpy()
        )
        ordered[name] = np.nan_to_num(values, nan=0.0)
        by_row = ordered.set_index("_row_id")[name]
        frame[name] = frame["_row_id"].map(by_row).fillna(0)
    return frame.drop(columns="_row_id")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["demo", "full"], default="demo")
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw"))
    parser.add_argument("--output", type=Path, default=Path("data/processed/features.parquet"))
    args = parser.parse_args()
    archive = download_dataset(args.raw_dir)
    frame = load_public_data(archive, maximum_rows=250_000 if args.profile == "demo" else None)
    validate_source(frame)
    result = materialize_features(enrich(clean_source(frame)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(args.output, index=False)
    print(json.dumps({"rows": len(result), "fraud_rate": result["is_fraud"].mean()}))


if __name__ == "__main__":
    main()
