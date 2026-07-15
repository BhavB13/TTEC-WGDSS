from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ForecastTrainingRow(Base):
    __tablename__ = "forecast_training_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feature_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    target_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    target_demand_mw: Mapped[float] = mapped_column(Float, nullable=False)

    current_demand_mw: Mapped[float] = mapped_column(Float, nullable=False)
    lag_1h_demand_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    lag_2h_demand_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    lag_3h_demand_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    lag_6h_demand_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    lag_24h_demand_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    rolling_3h_demand_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    rolling_6h_demand_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    rolling_24h_demand_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    demand_rate_1h_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    demand_rate_3h_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    demand_rate_6h_mw: Mapped[float | None] = mapped_column(Float, nullable=True)

    # These are contemporaneous SCADA operating-state values. They provide
    # context for observed demand without introducing future dispatch leakage.
    spinning_reserve_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    available_capacity_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    online_capacity_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    reserve_margin_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    online_spare_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    spinning_reserve_lag_1h_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    available_capacity_lag_1h_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    online_capacity_lag_1h_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    spinning_reserve_rate_1h_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    available_capacity_rate_1h_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    online_capacity_rate_1h_mw: Mapped[float | None] = mapped_column(Float, nullable=True)

    hour_of_day: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)

    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    scada_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_lag_1h_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    rolling_3h_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_rate_1h_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    rainfall_mm_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    cloud_cover_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_hpa: Mapped[float | None] = mapped_column(Float, nullable=True)

    forecast_temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    forecast_humidity_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    forecast_rainfall_mm_hr: Mapped[float | None] = mapped_column(Float, nullable=True)
    forecast_cloud_cover_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    forecast_wind_speed_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    forecast_precipitation_probability_percent: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )
    forecast_weather_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    forecast_weather_issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    source_quality_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="UNKNOWN",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "idx_forecast_training_rows_feature_horizon",
            "feature_timestamp",
            "horizon_hours",
            unique=True,
        ),
        Index("idx_forecast_training_rows_horizon", "horizon_hours"),
        Index("idx_forecast_training_rows_quality", "source_quality_status"),
    )


class DemandForecastResult(Base):
    __tablename__ = "demand_forecast_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    forecast_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_demand_mw: Mapped[float] = mapped_column(Float, nullable=False)
    forecast_uncertainty_mw: Mapped[float] = mapped_column(Float, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_name: Mapped[str] = mapped_column(String(100), nullable=False)
    baseline_forecast_mw: Mapped[float] = mapped_column(Float, nullable=False)
    mae: Mapped[float] = mapped_column(Float, nullable=False)
    rmse: Mapped[float] = mapped_column(Float, nullable=False)
    mape: Mapped[float] = mapped_column(Float, nullable=False)
    residual_std: Mapped[float] = mapped_column(Float, nullable=False)
    ml_beats_baseline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    feature_profile: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="demand_weather_v2",
    )
    validation_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="PROTOTYPE",
    )
    training_span_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    train_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    test_row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidate_metrics: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "idx_demand_forecast_results_timestamp_horizon",
            "forecast_timestamp",
            "horizon_hours",
        ),
        Index("idx_demand_forecast_results_quality", "quality_status"),
    )


class ScadaReplayForecastResult(Base):
    __tablename__ = "scada_replay_forecast_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_cursor_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    feature_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    forecast_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_demand_mw: Mapped[float] = mapped_column(Float, nullable=False)
    forecast_uncertainty_mw: Mapped[float] = mapped_column(Float, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_name: Mapped[str] = mapped_column(String(100), nullable=False)
    baseline_forecast_mw: Mapped[float] = mapped_column(Float, nullable=False)
    quality_status: Mapped[str] = mapped_column(String(32), nullable=False)
    mae: Mapped[float] = mapped_column(Float, nullable=False)
    rmse: Mapped[float] = mapped_column(Float, nullable=False)
    residual_std: Mapped[float] = mapped_column(Float, nullable=False)
    training_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    __table_args__ = (
        Index(
            "idx_scada_replay_forecast_cursor_horizon",
            "source_cursor_at",
            "horizon_hours",
            unique=True,
        ),
    )
