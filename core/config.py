from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    google_api_key: str = ""
    google_cloud_project: str = ""
    google_cloud_location: str = "us-central1"
    database_url: str = "sqlite+aiosqlite:///./reconciliation.db"
    app_env: str = "development"
    log_level: str = "INFO"
    app_base_url: str = "http://127.0.0.1:8000"
    
    # Authentication & JWT
    jwt_secret_key: str = "your-super-secret-jwt-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiration_hours: int = 24
    
    # Google Drive OAuth
    google_drive_client_id: str = os.getenv("GOOGLE_DRIVE_CLIENT_ID", "")
    google_drive_client_secret: str = os.getenv("GOOGLE_DRIVE_CLIENT_SECRET", "")
    google_drive_redirect_uri: str = os.getenv(
        "GOOGLE_DRIVE_REDIRECT_URI",
        "http://127.0.0.1:8000/api/v1/auth/google/callback",
    )


settings = Settings()
