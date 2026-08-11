"""Versioned domain contracts shared across HTTP and streaming boundaries."""

from datetime import UTC, datetime
from enum import StrEnum
from ipaddress import IPv4Address
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Decision(StrEnum):
    APPROVE = "APPROVE"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    BLOCK = "BLOCK"


class AlertStatus(StrEnum):
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"


class AlertResolution(StrEnum):
    FRAUD = "FRAUD"
    LEGITIMATE = "LEGITIMATE"


class Transaction(BaseModel):
    """Canonical payment event; labels are deliberately absent."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    transaction_id: str = Field(min_length=1, max_length=64)
    user_id: str = Field(min_length=1, max_length=64)
    merchant_id: str = Field(min_length=1, max_length=64)
    timestamp: datetime
    amount: float = Field(gt=0, le=10_000_000)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    merchant_category: str = Field(min_length=1, max_length=64)
    country: str = Field(min_length=2, max_length=2)
    device_id: str = Field(min_length=1, max_length=64)
    ip_address: IPv4Address
    channel: str = Field(default="web", pattern="^(web|mobile|pos)$")
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    request_id: UUID = Field(default_factory=uuid4)

    @field_validator("timestamp")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must include a timezone")
        return value.astimezone(UTC)

    @field_validator("currency", "country")
    @classmethod
    def uppercase_codes(cls, value: str) -> str:
        return value.upper()


class RiskFactor(BaseModel):
    feature: str
    impact: float
    direction: str = "increases_risk"


class Prediction(BaseModel):
    schema_version: str = "1.0"
    transaction_id: str
    fraud_probability: float = Field(ge=0, le=1)
    risk_score: int = Field(ge=0, le=100)
    decision: Decision
    model_version: str
    processing_time_ms: float = Field(ge=0)
    rule_reasons: list[str] = Field(default_factory=list)
    top_risk_factors: list[RiskFactor] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ConfirmedLabel(BaseModel):
    is_fraud: bool
    source: str = Field(default="analyst", min_length=1, max_length=32)
    confirmed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AlertUpdate(BaseModel):
    """A lightweight analyst case transition."""

    status: AlertStatus
    analyst_note: str | None = Field(default=None, max_length=2000)
    resolution: AlertResolution | None = None

    @model_validator(mode="after")
    def validate_resolution(self) -> Self:
        if self.status == AlertStatus.RESOLVED and self.resolution is None:
            raise ValueError("resolution is required when status is RESOLVED")
        if self.status != AlertStatus.RESOLVED and self.resolution is not None:
            raise ValueError("resolution is only valid when status is RESOLVED")
        return self
