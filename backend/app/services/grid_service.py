from __future__ import annotations

from typing import Any

from app.providers.grid_provider import GridProvider
from app.providers.mock_grid_provider import MockGridProvider


class GridService:
    def __init__(self, provider: GridProvider | None = None) -> None:
        self.provider = provider or MockGridProvider()

    async def get_generation_status(self) -> list[dict[str, Any]]:
        return await self.provider.get_generation_status()

    async def get_grid_status(self) -> dict[str, Any]:
        status = await self.provider.get_grid_status()
        return self._normalize_grid_status(status)

    async def get_grid_bundle(self) -> dict[str, Any]:
        generation_units = await self.get_generation_status()
        grid_status = await self.get_grid_status()
        if not grid_status.get("generation_units"):
            grid_status["generation_units"] = generation_units
        return grid_status

    def _normalize_grid_status(self, status: dict[str, Any]) -> dict[str, Any]:
        total_available_capacity_mw = float(status.get("total_available_capacity_mw", 0.0))
        current_generation_mw = float(status.get("current_generation_mw", status.get("total_generation_mw", 0.0)))
        current_demand_mw = float(status.get("current_demand_mw", current_generation_mw))
        reserve_margin_percent = float(
            status.get(
                "reserve_margin_percent",
                self._calculate_reserve_margin(total_available_capacity_mw, current_generation_mw),
            )
        )

        return {
            "timestamp": status.get("timestamp"),
            "current_demand_mw": current_demand_mw,
            "current_generation_mw": current_generation_mw,
            "total_available_capacity_mw": total_available_capacity_mw,
            "reserve_margin_percent": reserve_margin_percent,
            "grid_status": status.get("grid_status", "UNKNOWN"),
            "demand_period": status.get("demand_period", "UNKNOWN"),
            "source_provider": status.get("source_provider", "Unknown"),
            "generation_units": status.get("generation_units", []),
        }

    @staticmethod
    def _calculate_reserve_margin(
        total_available_capacity_mw: float,
        current_generation_mw: float,
    ) -> float:
        if current_generation_mw <= 0:
            return 0.0
        return round(
            ((total_available_capacity_mw - current_generation_mw) / current_generation_mw) * 100.0,
            2,
        )
