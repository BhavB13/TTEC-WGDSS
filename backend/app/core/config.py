# app/core/config.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "T&TEC Weather-Based Generation Decision Support System"
    API_V1_PREFIX: str = "/api"
    DEBUG: bool = False

    # Placeholder until PostgreSQL is implemented
    DATABASE_URL: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )


settings = Settings()