from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Forecast(Base):
    """
    Stores weather forecast data retrieved from weather providers.

    Each record represents a forecasted weather condition
    for a specific future timestamp.
    """

    __tablename__ = "forecasts"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    forecast_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    temperature_c: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    humidity_percent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    rainfall_mm_hr: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    cloud_cover_percent: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    wind_speed_kph: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    wind_direction_deg: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    precipitation_probability_percent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    precipitation_mm: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    weather_condition: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="Unknown",
    )

    heat_index_c: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    rain_severity: Mapped[str] = mapped_column(
        String(25),
        nullable=False,
        default="DRY",
    )

    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    provider_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "idx_forecast_timestamp_provider",
            "forecast_timestamp",
            "provider_name",
        ),
    )
