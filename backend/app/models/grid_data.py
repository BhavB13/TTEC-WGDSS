from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GridData(Base):
    __tablename__ = "grid_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    current_demand_mw: Mapped[float] = mapped_column(Float, nullable=False)
    current_generation_mw: Mapped[float] = mapped_column(Float, nullable=False)
    total_available_capacity_mw: Mapped[float] = mapped_column(Float, nullable=False)
    reserve_margin_percent: Mapped[float] = mapped_column(Float, nullable=False)

    grid_status: Mapped[str] = mapped_column(String(25), nullable=False)
    demand_period: Mapped[str] = mapped_column(String(25), nullable=False)
    source_provider: Mapped[str] = mapped_column(String(100), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_grid_data_timestamp", "timestamp"),
        Index("idx_grid_data_provider", "source_provider"),
    )
