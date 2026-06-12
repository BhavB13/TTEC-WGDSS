from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Weather(Base):
    """
    Stores weather observations from weather providers.

    Each record represents a weather snapshot collected from a
    provider such as Open-Meteo or WeatherAPI.
    """

    __tablename__ = "weather_observations"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True
    )

    temperature_c: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    humidity_percent: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    wind_speed_kph: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    wind_direction_deg: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    pressure_hpa: Mapped[float] = mapped_column(
        Float,
        nullable=False
    )

    precipitation_mm: Mapped[float | None] = mapped_column(
        Float,
        nullable=True
    )

    provider_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    __table_args__ = (
        Index(
            "idx_provider_created_at",
            "provider_name",
            "created_at"
        ),
    )