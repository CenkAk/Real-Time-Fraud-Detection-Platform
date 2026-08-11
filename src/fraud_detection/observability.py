"""Structured logging and Prometheus metrics."""

import logging
import sys

from prometheus_client import Counter, Histogram
from pythonjsonlogger.json import JsonFormatter

TRANSACTIONS = Counter("fraud_transactions_total", "Transactions scored", ["decision"])
ERRORS = Counter("fraud_errors_total", "Processing errors", ["component", "error_type"])
INFERENCE_LATENCY = Histogram(
    "fraud_inference_latency_seconds",
    "End-to-end feature and inference latency",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)
EVENT_LATENCY = Histogram("fraud_event_latency_seconds", "Event processing latency")


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
