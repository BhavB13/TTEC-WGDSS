from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class GridData(Base):
    __tablename__ = "grid_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    snapshot_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    current_demand_mw: Mapped[float] = mapped_column(Float, nullable=False)
    current_generation_mw: Mapped[float] = mapped_column(Float, nullable=False)
    total_available_capacity_mw: Mapped[float] = mapped_column(Float, nullable=False)
    reserve_margin_percent: Mapped[float] = mapped_column(Float, nullable=False)
    spinning_reserve_mw: Mapped[float | None] = mapped_column(Float, nullable=True)
    spinning_reserve_source: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    grid_status: Mapped[str] = mapped_column(String(25), nullable=False)
    demand_period: Mapped[str] = mapped_column(String(25), nullable=False)
    source_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    quality_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="GOOD",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("idx_grid_data_timestamp", "timestamp"),
        Index("idx_grid_data_provider", "source_provider"),
    )
