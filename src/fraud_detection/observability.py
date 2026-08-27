import logging
import sys
from contextvars import ContextVar

from prometheus_client import Counter, Gauge, Histogram
from pythonjsonlogger.json import JsonFormatter

REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)

HTTP_REQUESTS = Counter(
    "fraud_http_requests_total", "HTTP requests", ["method", "route", "status"]
)
HTTP_REQUEST_LATENCY = Histogram(
    "fraud_http_request_latency_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)
TRANSACTIONS = Counter("fraud_transactions_total", "Transactions scored", ["decision"])
ERRORS = Counter("fraud_errors_total", "Processing errors", ["component", "error_type"])
WORKER_EVENTS = Counter("fraud_worker_events_total", "Worker events", ["result"])
DLQ_EVENTS = Counter("fraud_dlq_events_total", "Events routed to the dead-letter topic")
CONSUMER_LAG = Gauge(
    "fraud_consumer_lag", "Approximate Kafka consumer lag", ["group", "topic", "partition"]
)
OUTBOX_PENDING = Gauge("fraud_outbox_pending", "Unpublished transactional outbox events")
OUTBOX_OLDEST_AGE = Gauge(
    "fraud_outbox_oldest_age_seconds", "Age of the oldest unpublished outbox event"
)
INFERENCE_LATENCY = Histogram(
    "fraud_inference_latency_seconds",
    "End-to-end feature and inference latency",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
)
EVENT_LATENCY = Histogram(
    "fraud_event_latency_seconds",
    "Event timestamp to completed decision latency",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = REQUEST_ID.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestContextFilter())
    handler.setFormatter(
        JsonFormatter("%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
