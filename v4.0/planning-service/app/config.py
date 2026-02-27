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
    rate_limit_requests_per_window: int = 30
    log_level: str = "INFO"


settings = Settings()
