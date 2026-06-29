from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "T&TEC Weather-Based Generation Decision Support System"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173,http://127.0.0.1:5173"

    DATABASE_URL: str = "sqlite:///./wgdss.db"
    DB_ECHO: bool = False

    OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com/v1/forecast"
    MET_NORWAY_BASE_URL: str = (
        "https://api.met.no/weatherapi/locationforecast/2.0/compact"
    )
    MET_NORWAY_USER_AGENT: str = "TTEC-WGDSS/1.0 (+https://www.ttec.co.tt/)"
    WEATHER_API_BASE_URL: str = "https://api.weatherapi.com/v1"
    WEATHER_API_KEY: str = ""
    ENABLE_WEATHERAPI_FALLBACK: bool = False

    # Piarco is a low-elevation, operationally representative Trinidad location.
    DEFAULT_LATITUDE: float = 10.5953
    DEFAULT_LONGITUDE: float = -61.3372
    WEATHER_SITE_ALTITUDE_METERS: int = 12

    WEATHER_TIMEOUT_SECONDS: float = 10.0
    WEATHER_RETRY_ATTEMPTS: int = 3
    WEATHER_RETRY_BACKOFF_SECONDS: float = 0.75
    WEATHER_CACHE_TTL_SECONDS: int = 300
    WEATHER_CONSENSUS_TIMEOUT_SECONDS: float = 12.0
    OPEN_METEO_DAILY_REQUEST_LIMIT: int = 9000
    WEATHER_API_MONTHLY_REQUEST_LIMIT: int = 90000
    DATABASE_AUTO_CREATE: bool = True
    CALIBRATION_DATA_ZIP_PATH: str = ""
    CALIBRATION_AUTO_IMPORT: bool = False
    SNAPSHOT_PERSISTENCE_ENABLED: bool = True
    DATA_STALE_AFTER_SECONDS: int = 5400

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
    )

    @field_validator("DEBUG", mode="before")
    @classmethod
    def _coerce_debug(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off", "release"}:
                return False
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.CORS_ALLOWED_ORIGINS.split(",")
            if origin.strip() and origin.strip() != "*"
        ]


settings = Settings()
