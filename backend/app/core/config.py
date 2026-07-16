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
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE_SECONDS: int = 1800

    OPEN_METEO_BASE_URL: str = "https://api.open-meteo.com/v1/forecast"
    OPEN_METEO_ARCHIVE_URL: str = "https://archive-api.open-meteo.com/v1/archive"
    OPEN_METEO_SINGLE_RUNS_URL: str = (
        "https://single-runs-api.open-meteo.com/v1/forecast"
    )
    REPLAY_WEATHER_MODELS: str = "ecmwf_ifs025,gfs_global,icon_global"
    REPLAY_WEATHER_RUN_AVAILABILITY_LAG_HOURS: int = 6
    REPLAY_WEATHER_CACHE_TTL_SECONDS: int = 21600
    MET_NORWAY_BASE_URL: str = (
        "https://api.met.no/weatherapi/locationforecast/2.0/compact"
    )
    MET_NORWAY_USER_AGENT: str = "TTEC-WGDSS/1.0 (+https://www.ttec.co.tt/)"
    WEATHER_API_BASE_URL: str = "https://api.weatherapi.com/v1"
    WEATHER_API_KEY: str = ""
    ENABLE_WEATHERAPI_FALLBACK: bool = False
    NHC_CURRENT_STORMS_URL: str = "https://www.nhc.noaa.gov/CurrentStorms.json"
    NHC_STORM_TRACKING_TIMEOUT_SECONDS: float = 10.0
    NHC_STORM_TRACKING_CACHE_TTL_SECONDS: int = 900
    NHC_USER_AGENT: str = "TTEC-WGDSS/1.0 (+https://www.ttec.co.tt/)"

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
    GRID_PROVIDER: str = "mock"
    GRID_STALE_AFTER_SECONDS: int = 30
    MODEL_FORECAST_STALE_AFTER_SECONDS: int = 7200
    FORECAST_EXTRA_HOLIDAY_DATES: str = ""
    DEMO_REPLAY_ENABLED: bool = True
    DEMO_REPLAY_AUTO_SEED: bool = True
    DEMO_DATASET_YEAR: int = 2025
    DEMO_REPLAY_MONTH: int = 6
    SCADA_REPLAY_ARCHIVE_PATH: str = ""
    SCADA_HISTORICAL_WEATHER_BACKFILL: bool = False

    # Historical trend-export policy. These defaults preserve current prototype
    # behavior and are not confirmed T&TEC/OSI production rules.
    SCADA_STRICT_QUALITY_VALUES: str = "Good"
    SCADA_CONDITIONAL_QUALITY_VALUES: str = "Other"
    SCADA_MIN_HOURLY_COVERAGE: float = 0.90
    SCADA_MAX_HOURLY_COVERAGE: float = 1.05
    SCADA_EXPECTED_REPORTING_START: str = ""
    SCADA_EXPECTED_REPORTING_END: str = ""

    # Operator-policy assumptions are configurable and remain explicitly
    # unconfirmed until T&TEC control engineering approves them.
    OPERATING_POLICY_STATUS: str = "PROTOTYPE_UNCONFIRMED"
    OPERATING_RESERVE_FRACTION: float = 0.15
    RISK_MEDIUM_PROBABILITY_THRESHOLD: float = 0.30
    RISK_HIGH_PROBABILITY_THRESHOLD: float = 0.65
    FAST_START_UNIT_CAPACITY_MW: float = 15.0
    FAST_START_MAX_CAPACITY_MW: float = 30.0
    FAST_START_LEAD_TIME_MINUTES: int = 20
    HEAVY_START_MIN_CAPACITY_MW: float = 60.0
    HEAVY_START_MAX_CAPACITY_MW: float = 120.0
    HEAVY_START_LEAD_TIME_MINUTES: int = 60

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
