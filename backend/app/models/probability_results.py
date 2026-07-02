from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProbabilityResult(Base):
    __tablename__ = "probability_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )

    probability_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    forecast_demand_30m: Mapped[float] = mapped_column(Float, nullable=False)
    forecast_demand_60m: Mapped[float] = mapped_column(Float, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(64), nullable=False)
    factors: Mapped[str] = mapped_column(Text, nullable=False)
    engine_version: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="unknown",
    )
    weather_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    grid_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    weather_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    grid_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_quality_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="UNKNOWN",
    )
    calibration_scenario: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_probability_results_created_at", "created_at"),
        Index("idx_probability_results_risk_level", "risk_level"),
    )
