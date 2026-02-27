from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Tamil Nadu Fiber Planning Service"
    app_description: str = "PostGIS + pgRouting constrained routing API"
    app_version: str = "0.1.0"
    cors_allow_origins: str = "*"

    database_url: str = "postgresql://postgres:postgres@localhost:5432/gis_tn"
    pgrouting_tolerance_degrees: float = 0.00001
    default_cost_per_meter: float = 700.0
    max_batch_coordinates: int = 50000
    batch_chunk_size: int = 1000
    max_request_body_bytes: int = 5_000_000
    rate_limit_window_seconds: int = 60
    rate_limit_requests_per_window: int = 10
    request_timeout_seconds: int = 30
    mock_chunk_delay_seconds: float = 0.02
    job_retention_seconds: int = 300
    executor_max_workers: int = 3
    max_active_jobs: int = 5
    chunk_timeout_seconds: int = 30
    chunk_executor_max_workers: int = 8
    max_stored_results_memory_mb: int = 200
    log_level: str = "INFO"


settings = Settings()
