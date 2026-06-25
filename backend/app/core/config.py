from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "T&TEC Weather-Based Generation Decision Support System"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    DATABASE_URL: str = "sqlite:///./wgdss.db"
    DB_ECHO: bool = False

    OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com/v1/forecast"
    WEATHER_API_BASE_URL: str = "https://api.weatherapi.com/v1"
    WEATHER_API_KEY: str = ""

    DEFAULT_LATITUDE: float = 10.6918
    DEFAULT_LONGITUDE: float = -61.2225

    WEATHER_TIMEOUT_SECONDS: float = 10.0
    WEATHER_RETRY_ATTEMPTS: int = 3
    WEATHER_RETRY_BACKOFF_SECONDS: float = 0.75
    WEATHER_CACHE_TTL_SECONDS: int = 300

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )


settings = Settings()
