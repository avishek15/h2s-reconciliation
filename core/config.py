from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    google_api_key: str = ""
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    database_url: str = "sqlite+aiosqlite:///./reconciliation.db"
    app_env: str = "development"
    log_level: str = "INFO"


settings = Settings()
