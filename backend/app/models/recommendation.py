from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Recommendation(Base):
    """
    Stores generation recommendations produced by the
    recommendation engine.

    Each recommendation represents a decision generated
    from weather conditions, forecast data, and generation
    system status.
    """

    __tablename__ = "recommendations"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    probability_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    risk_level: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="LOW",
    )

    forecast_demand_30m: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    forecast_demand_60m: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )

    recommendation: Mapped[str] = mapped_column(
        String(25),
        nullable=False,
    )

    reason: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    factors: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="[]",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "idx_recommendation_created_at",
            "created_at",
        ),
        Index(
            "idx_recommendation_type",
            "recommendation",
        ),
    )
