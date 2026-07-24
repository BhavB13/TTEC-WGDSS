from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.config import settings
from app.providers.grid_provider import GridProvider
from app.schemas.grid import GenerationUnitResponse, GridStatusResponse


@dataclass(frozen=True)
class HistorianProviderHealth:
    status: str
    read_only: bool
    watermark: datetime | None
    detail: str


class HistorianGridProvider(GridProvider):
    """Configuration-disabled boundary for a future approved read-only adapter."""

    REQUIRED_CONFIGURATION = (
        "HISTORIAN_ENDPOINT",
        "HISTORIAN_AUTH_MODE",
        "HISTORIAN_CA_CERT_PATH",
        "HISTORIAN_TAG_MAP_JSON",
        "HISTORIAN_UNITS_JSON",
        "HISTORIAN_QUALITY_POLICY",
        "HISTORIAN_NETWORK_ZONE",
    )

    def __init__(self) -> None:
        missing = [
            name for name in self.REQUIRED_CONFIGURATION
            if not str(getattr(settings, name, "")).strip()
        ]
        if not settings.HISTORIAN_READ_ONLY_ENABLED or missing:
            detail = (
                "Historian integration is disabled"
                if not settings.HISTORIAN_READ_ONLY_ENABLED
                else "Missing approved configuration: " + ", ".join(missing)
            )
            raise RuntimeError(detail)
        raise RuntimeError(
            "Historian transport adapter is not installed; configuration alone "
            "cannot enable an unapproved OT connection"
        )

    async def get_grid_status(self) -> GridStatusResponse:
        raise RuntimeError("Historian provider is unavailable")

    async def get_generation_status(self) -> list[GenerationUnitResponse]:
        raise RuntimeError("Historian provider is unavailable")

    async def latest_values(self) -> dict[str, object]:
        raise RuntimeError("Historian provider is unavailable")

    async def range_values(
        self,
        start_at: datetime,
        end_at: datetime,
    ) -> list[dict[str, object]]:
        raise RuntimeError("Historian provider is unavailable")

    async def health(self) -> HistorianProviderHealth:
        return HistorianProviderHealth(
            status="DISABLED",
            read_only=True,
            watermark=None,
            detail="No approved historian transport is configured",
        )

    async def watermark(self) -> datetime | None:
        return None
