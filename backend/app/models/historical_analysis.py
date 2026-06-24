from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class HistoricalAnalysis(Base):
    __tablename__ = "historical_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    analysis_name: Mapped[str] = mapped_column(String(150), nullable=False)
    analysis_period: Mapped[str] = mapped_column(String(75), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_historical_analysis_created_at", "created_at"),
        Index("idx_historical_analysis_name", "analysis_name"),
    )
