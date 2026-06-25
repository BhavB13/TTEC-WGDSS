from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Generation(Base):
    """
    Stores operational information for generation units.

    Each record represents the current state of a generating unit
    and can be used by the recommendation engine when evaluating
    startup and dispatch decisions.
    """

    __tablename__ = "generation_units"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    station_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    unit_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    fuel_type: Mapped[str] = mapped_column(
        String(25),
        nullable=False,
    )

    available_capacity_mw: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    current_output_mw: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(25),
        nullable=False,
    )

    is_dispatchable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index(
            "idx_station_unit",
            "station_name",
            "unit_name",
        ),
        Index(
            "idx_generation_status",
            "status",
        ),
    )