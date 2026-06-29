from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Any

from app.data.mock_generation_data import MOCK_GENERATION_UNITS
from app.providers.grid_provider import GridProvider

logger = logging.getLogger(__name__)


class MockGridProvider(GridProvider):
    def _current_local_hour(self) -> int:
        return datetime.now(ZoneInfo("America/Port_of_Spain")).hour

    def _demand_period(self, hour: int) -> tuple[str, float]:
        if 0 <= hour < 6:
            return "NIGHT", 700.0
        if 6 <= hour < 12:
            return "MORNING", 850.0
        if 12 <= hour < 17:
            return "AFTERNOON", 950.0
        if 17 <= hour < 22:
            return "EVENING_PEAK", 1000.0
        return "LATE_NIGHT", 750.0

    async def get_generation_status(self) -> list[dict[str, Any]]:
        logger.debug("Returning mock generation status")
        return MOCK_GENERATION_UNITS

    async def get_grid_status(self) -> dict[str, Any]:
        generation_units = await self.get_generation_status()
        total_available_capacity_mw = sum(
            unit["available_capacity_mw"] for unit in generation_units
        )
        current_generation_mw = sum(
            unit["current_output_mw"] for unit in generation_units
        )

        demand_period, current_demand_mw = self._demand_period(self._current_local_hour())
        reserve_margin_percent = round(
            ((total_available_capacity_mw - current_demand_mw) / max(current_demand_mw, 1.0))
            * 100.0,
            2,
        )

        if reserve_margin_percent < 10:
            grid_status = "CRITICAL"
        elif reserve_margin_percent < 20:
            grid_status = "WATCH"
        else:
            grid_status = "NORMAL"

        return {
            "timestamp": datetime.now(ZoneInfo("America/Port_of_Spain")).isoformat(),
            "current_demand_mw": current_demand_mw,
            "current_generation_mw": round(current_generation_mw, 2),
            "total_available_capacity_mw": round(total_available_capacity_mw, 2),
            "reserve_margin_percent": reserve_margin_percent,
            "grid_status": grid_status,
            "demand_period": demand_period,
            "source_provider": "MockGridProvider",
            "generation_units": generation_units,
        }
