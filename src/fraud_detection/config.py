from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite+pysqlite:///./fraud.db"
    kafka_bootstrap_servers: str = "localhost:19092"
    model_path: str = "artifacts/models/champion.joblib"
    mlflow_tracking_uri: str = "http://localhost:5000"
    fraud_review_threshold: float = Field(default=0.40, ge=0, le=1)
    fraud_block_threshold: float = Field(default=0.70, ge=0, le=1)
    use_model_thresholds: bool = True
    review_cost: float = Field(default=5.0, ge=0)
    false_positive_cost: float = Field(default=25.0, ge=0)
    review_catch_rate: float = Field(default=0.80, ge=0, le=1)
    max_review_rate: float = Field(default=0.05, ge=0, le=1)
    simulator_rate_per_second: float = Field(default=2.0, gt=0)
    simulator_seed: int = 42
    explanation_enabled: bool = True

    @model_validator(mode="after")
    def validate_threshold_order(self) -> "Settings":
        if self.fraud_review_threshold >= self.fraud_block_threshold:
            raise ValueError("review threshold must be lower than block threshold")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
