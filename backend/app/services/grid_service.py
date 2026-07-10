from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from app.providers.grid_provider import GridProvider
from app.providers.grid_provider_factory import create_grid_provider
from app.schemas.grid import GridStatusResponse, TelemetryQuality
from app.services.provider_health import record_provider_failure, record_provider_success


class GridDataValidationError(ValueError):
    pass


class GridService:
    def __init__(self, provider: GridProvider | None = None) -> None:
        self.provider = provider or create_grid_provider()

    async def get_generation_status(self) -> list[dict[str, Any]]:
        try:
            units = await self.provider.get_generation_status()
            record_provider_success("grid_provider", self.provider.__class__.__name__)
        except Exception as exc:
            record_provider_failure(
                "grid_provider",
                self.provider.__class__.__name__,
                exc,
            )
            raise
        return [unit.model_dump(mode="json") for unit in units]

    async def get_grid_status(self) -> dict[str, Any]:
        try:
            status = await self.provider.get_grid_status()
            record_provider_success("grid_provider", self.provider.__class__.__name__)
        except Exception as exc:
            record_provider_failure(
                "grid_provider",
                self.provider.__class__.__name__,
                exc,
            )
            raise
        return self._normalize_grid_status(status)

    async def get_grid_bundle(self) -> dict[str, Any]:
        generation_units = await self.get_generation_status()
        grid_status = await self.get_grid_status()
        if not grid_status.get("generation_units"):
            grid_status["generation_units"] = generation_units
        return grid_status

    def _normalize_grid_status(
        self,
        status: GridStatusResponse | Mapping[str, Any],
    ) -> dict[str, Any]:
        payload = (
            status.model_dump(mode="json")
            if isinstance(status, GridStatusResponse)
            else dict(status)
        )
        required_fields = (
            "current_demand_mw",
            "current_generation_mw",
            "total_available_capacity_mw",
        )
        missing_fields = [
            field
            for field in required_fields
            if payload.get(field) is None
        ]
        if missing_fields:
            raise GridDataValidationError(
                "Grid provider omitted critical telemetry: "
                + ", ".join(missing_fields)
            )

        current_demand_mw = self._required_non_negative(payload, "current_demand_mw")
        current_generation_mw = self._required_non_negative(
            payload,
            "current_generation_mw",
        )
        total_available_capacity_mw = self._required_non_negative(
            payload,
            "total_available_capacity_mw",
        )
        if current_generation_mw > total_available_capacity_mw:
            raise GridDataValidationError(
                "Current generation exceeds available capacity"
            )

        reserve_margin_percent = self._calculate_reserve_margin(
            total_available_capacity_mw,
            current_demand_mw,
        )
        quality_status = str(payload.get("quality_status", TelemetryQuality.GOOD))
        timestamp = payload.get("timestamp")
        received_at = payload.get("received_at") or datetime.now(timezone.utc).isoformat()

        return {
            "timestamp": timestamp,
            "received_at": received_at,
            "current_demand_mw": current_demand_mw,
            "current_generation_mw": current_generation_mw,
            "total_available_capacity_mw": total_available_capacity_mw,
            "reserve_margin_percent": reserve_margin_percent,
            "grid_status": payload.get("grid_status", "UNKNOWN"),
            "demand_period": payload.get("demand_period", "UNKNOWN"),
            "source_provider": payload.get("source_provider", "Unknown"),
            "generation_units": payload.get("generation_units", []),
            "quality_status": quality_status,
            "missing_fields": missing_fields,
        }

    @staticmethod
    def _calculate_reserve_margin(
        total_available_capacity_mw: float,
        current_demand_mw: float,
    ) -> float:
        if current_demand_mw <= 0:
            return 0.0
        return round(
            ((total_available_capacity_mw - current_demand_mw) / current_demand_mw)
            * 100.0,
            2,
        )

    @staticmethod
    def _required_non_negative(payload: Mapping[str, Any], field: str) -> float:
        try:
            value = float(payload[field])
        except (KeyError, TypeError, ValueError) as exc:
            raise GridDataValidationError(
                f"Grid telemetry {field!r} is not numeric"
            ) from exc
        if value < 0:
            raise GridDataValidationError(
                f"Grid telemetry {field!r} cannot be negative"
            )
        return value
