from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DemoObservation(Base):
    """Immutable hourly SCADA/weather observation used by the demo replay."""

    __tablename__ = "demo_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), unique=True, nullable=False)
    demand_mw: Mapped[float] = mapped_column(Float, nullable=False)
    generation_mw: Mapped[float] = mapped_column(Float, nullable=False)
    spinning_reserve_mw: Mapped[float] = mapped_column(Float, nullable=False)
    available_capacity_mw: Mapped[float] = mapped_column(Float, nullable=False)
    online_capacity_mw: Mapped[float] = mapped_column(Float, nullable=False)
    temperature_c: Mapped[float] = mapped_column(Float, nullable=False)
    humidity_percent: Mapped[float] = mapped_column(Float, nullable=False)
    rainfall_mm_hr: Mapped[float] = mapped_column(Float, nullable=False)
    cloud_cover_percent: Mapped[float] = mapped_column(Float, nullable=False)
    wind_speed_kmh: Mapped[float] = mapped_column(Float, nullable=False)
    wind_direction_deg: Mapped[float] = mapped_column(Float, nullable=False)
    pressure_hpa: Mapped[float] = mapped_column(Float, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(24), nullable=False, default="GOOD")
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_demo_observations_timestamp", "timestamp"),
        Index("ix_demo_observations_quality", "quality_status"),
    )


class DemoReplayState(Base):
    """Persistent playback cursor; observation rows remain immutable."""

    __tablename__ = "demo_replay_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    dataset_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dataset_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    replay_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    replay_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cursor_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_playing: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    step_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    speed_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=3600.0)
    last_wallclock_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
