from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ProbabilityResult(Base):
    __tablename__ = "probability_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    probability_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False)
    forecast_demand_30m: Mapped[float] = mapped_column(Float, nullable=False)
    forecast_demand_60m: Mapped[float] = mapped_column(Float, nullable=False)
    recommendation: Mapped[str] = mapped_column(String(64), nullable=False)
    factors: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_probability_results_created_at", "created_at"),
        Index("idx_probability_results_risk_level", "risk_level"),
    )
