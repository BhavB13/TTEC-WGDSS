from typing import Any

from app.providers.grid_provider import GridProvider


class MockGridProvider(GridProvider):
    """
    Mock implementation of the GridProvider.
    """

    async def get_generation_status(self) -> list[dict[str, Any]]:
        return [
            {
                "station_name": "Point Lisas",
                "unit_name": "GT-1",
                "available_capacity_mw": 120.0,
                "current_output_mw": 95.0,
                "status": "ONLINE",
            }
        ]

    async def get_grid_status(self) -> dict[str, Any]:
        return {
            "reserve_margin_percent": 15,
            "total_available_capacity_mw": 120.0,
            "total_generation_mw": 95.0,
            "grid_status": "NORMAL",
        }